"""Compare OpenAI models side-by-side on real Doornegar data.

Tests the EXACT same prompts used in production (bias scoring +
story analysis) against multiple models, using real articles/stories
from the database. Writes a markdown file you can open in your editor
and judge quality by eye.

Usage:
    cd backend
    python -m scripts.compare_models

Outputs:
    backend/model_comparison_results.md

Estimated cost per run: ~$0.50-1.00 (40 bias calls + 20 summary calls).
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import openai

from app.config import settings
from app.database import async_session
from app.models.article import Article
from app.models.source import Source
from app.models.story import Story
from app.services.bias_scoring import BIAS_ANALYSIS_PROMPT, FRAMING_LABELS
from app.services.story_analysis import STORY_ANALYSIS_PROMPT, ALIGNMENT_LABELS_FA

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("compare")

# ─── Models to compare ─────────────────────────────────────────
MODELS = [
    "gpt-4o-mini",     # current production baseline
    "gpt-4.1-nano",    # safest downgrade candidate
    "gpt-5-nano",      # cheapest candidate
    "gpt-5-mini",      # upgrade candidate (better reasoning)
]

# ─── Sample sizes ─────────────────────────────────────────────
NUM_BIAS_ARTICLES = 10   # articles to score for bias comparison
NUM_SUMMARY_STORIES = 5  # stories to summarize

OUTPUT_FILE = Path(__file__).parent.parent / "model_comparison_results.md"


async def pick_diverse_articles(db, n: int = 10) -> list[Article]:
    """Pick articles spanning different source alignments."""
    articles = []
    for alignment in ("state", "semi_state", "independent", "diaspora"):
        per_alignment = max(1, n // 4)
        result = await db.execute(
            select(Article)
            .join(Source, Article.source_id == Source.id)
            .where(
                Source.state_alignment == alignment,
                Article.content_text.isnot(None),
                Article.title_original.isnot(None),
            )
            .limit(per_alignment * 3)  # grab more so we can randomize
        )
        candidates = list(result.scalars().all())
        random.shuffle(candidates)
        articles.extend(candidates[:per_alignment])

    random.shuffle(articles)
    return articles[:n]


async def pick_stories_with_articles(db, n: int = 5) -> list[tuple[Story, list[dict]]]:
    """Pick stories that have at least 3 articles with content."""
    result = await db.execute(
        select(Story)
        .where(Story.article_count >= 3)
        .order_by(Story.created_at.desc())
        .limit(n * 3)
    )
    candidates = list(result.scalars().all())
    random.shuffle(candidates)

    chosen = []
    for story in candidates:
        art_result = await db.execute(
            select(Article, Source)
            .join(Source, Article.source_id == Source.id)
            .where(
                Article.story_id == story.id,
                Article.content_text.isnot(None),
            )
            .limit(6)
        )
        articles_with_sources = []
        for art, src in art_result.all():
            articles_with_sources.append({
                "title": art.title_original or art.title_fa or "",
                "content": (art.content_text or "")[:2000],
                "source_name_fa": src.name_fa or src.name_en or "",
                "state_alignment": src.state_alignment or "",
            })
        if len(articles_with_sources) >= 3:
            chosen.append((story, articles_with_sources))
        if len(chosen) >= n:
            break
    return chosen


async def call_model(client, model: str, prompt: str, max_tokens: int = 1500) -> dict:
    """Call a model and return dict with response, latency, tokens."""
    t0 = time.time()
    try:
        # gpt-5 family uses a different parameter name
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if model.startswith("gpt-5"):
            kwargs["max_completion_tokens"] = max_tokens
            # gpt-5-* only supports temperature=1 (default); don't pass it
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = 0.3
        resp = await client.chat.completions.create(**kwargs)
        elapsed = time.time() - t0
        return {
            "ok": True,
            "text": resp.choices[0].message.content or "",
            "elapsed_s": round(elapsed, 1),
            "input_tokens": resp.usage.prompt_tokens if resp.usage else None,
            "output_tokens": resp.usage.completion_tokens if resp.usage else None,
        }
    except Exception as e:
        return {"ok": False, "text": f"ERROR: {e}", "elapsed_s": round(time.time() - t0, 1)}


def try_parse_json(text: str) -> dict | None:
    """Extract JSON from a response, tolerating code fences."""
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(t)
    except Exception:
        return None


def format_bias_row(model: str, result: dict) -> str:
    """Format one model's bias score as a markdown row."""
    if not result["ok"]:
        return f"| **{model}** | — | — | — | — | — | `{result['text'][:80]}` |"
    scores = try_parse_json(result["text"])
    if not scores:
        return f"| **{model}** | PARSE ERROR | | | | | `{result['text'][:80]}` |"
    pa = scores.get("political_alignment")
    pa_str = f"{pa:+.2f}" if isinstance(pa, (int, float)) else "—"
    fact = scores.get("factuality_score")
    fact_str = f"{fact:.2f}" if isinstance(fact, (int, float)) else "—"
    tone = scores.get("tone_score")
    tone_str = f"{tone:+.2f}" if isinstance(tone, (int, float)) else "—"
    emo = scores.get("emotional_language_score")
    emo_str = f"{emo:.2f}" if isinstance(emo, (int, float)) else "—"
    framing = ", ".join(scores.get("framing_labels", [])[:3]) or "—"
    reasoning = scores.get("reasoning_en", "") or ""
    return (
        f"| **{model}** | {pa_str} | {tone_str} | {fact_str} | {emo_str} | {framing} | "
        f"{reasoning[:150]} |"
    )


async def compare_bias(client, articles: list[Article]) -> list[str]:
    """Run bias scoring on each article with all models. Returns markdown blocks."""
    blocks = ["# Bias Scoring Comparison\n"]
    blocks.append(f"Tested {len(articles)} articles across {len(MODELS)} models.\n")

    for i, article in enumerate(articles, 1):
        # Load source info
        async with async_session() as db:
            src_result = await db.execute(
                select(Source).where(Source.id == article.source_id)
            )
            source = src_result.scalar_one_or_none()

        alignment = source.state_alignment if source else "unknown"
        source_name = (source.name_fa or source.name_en) if source else "unknown"
        text = (article.content_text or article.summary or "")[:8000]
        prompt = BIAS_ANALYSIS_PROMPT.format(
            title=article.title_original,
            text=text,
            framing_labels=json.dumps(FRAMING_LABELS),
        )

        blocks.append(f"\n---\n\n## Article {i} — from {source_name} ({alignment})\n")
        blocks.append(f'**Title**: {article.title_original}\n')
        blocks.append(f'**Preview**: {text[:300]}...\n')
        blocks.append("\n| Model | pol. align | tone | factuality | emotional | framing | reasoning |")
        blocks.append("|---|---|---|---|---|---|---|")

        for model in MODELS:
            logger.info(f"  bias [{i}/{len(articles)}] {model}")
            result = await call_model(client, model, prompt, max_tokens=1200)
            blocks.append(format_bias_row(model, result))

    return blocks


async def compare_summary(client, stories) -> list[str]:
    """Run story summarization with all models. Returns markdown blocks."""
    blocks = ["\n\n# Story Summary Comparison\n"]
    blocks.append(f"Tested {len(stories)} stories across {len(MODELS)} models.\n")

    for i, (story, articles_with_sources) in enumerate(stories, 1):
        # Build the prompt exactly like production does
        lines = []
        for j, art in enumerate(articles_with_sources, 1):
            alignment_fa = ALIGNMENT_LABELS_FA.get(art.get("state_alignment", ""), "نامشخص")
            lines.append(f"--- مقاله {j} ---")
            lines.append(f"عنوان: {art.get('title', '')}")
            lines.append(f"منبع: {art.get('source_name_fa', '')} (جهت‌گیری: {alignment_fa})")
            if art.get("content"):
                lines.append(f"متن: {art.get('content')}")
            lines.append("")
        articles_block = "\n".join(lines)
        prompt = STORY_ANALYSIS_PROMPT.format(articles_block=articles_block)

        blocks.append(f"\n---\n\n## Story {i}: {story.title_fa or story.title_en or ''}\n")
        blocks.append(f"**Articles in story**: {story.article_count}\n")
        sources_line = ", ".join(set(a["source_name_fa"] for a in articles_with_sources))
        blocks.append(f"**Sources**: {sources_line}\n")

        for model in MODELS:
            logger.info(f"  summary [{i}/{len(stories)}] {model}")
            result = await call_model(client, model, prompt, max_tokens=2000)
            blocks.append(f"\n### {model}")
            blocks.append(f"*({result['elapsed_s']}s, "
                          f"in={result.get('input_tokens')}, "
                          f"out={result.get('output_tokens')})*\n")
            if not result["ok"]:
                blocks.append(f"❌ {result['text'][:300]}\n")
                continue
            parsed = try_parse_json(result["text"])
            if not parsed:
                blocks.append(f"⚠ Parse error. Raw output:\n```\n{result['text'][:500]}\n```\n")
                continue
            blocks.append(f"**Overall summary**: {parsed.get('summary_fa') or '—'}\n")
            if parsed.get("state_summary_fa"):
                blocks.append(f"**State perspective**: {parsed['state_summary_fa']}\n")
            if parsed.get("diaspora_summary_fa"):
                blocks.append(f"**Diaspora perspective**: {parsed['diaspora_summary_fa']}\n")
            if parsed.get("independent_summary_fa"):
                blocks.append(f"**Independent perspective**: {parsed['independent_summary_fa']}\n")
            if parsed.get("bias_explanation_fa"):
                blocks.append(f"**Bias explanation**: {parsed['bias_explanation_fa']}\n")

    return blocks


async def main():
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set. Set it in .env or env var.")
        return

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    logger.info(f"Picking {NUM_BIAS_ARTICLES} diverse articles + {NUM_SUMMARY_STORIES} stories...")
    async with async_session() as db:
        articles = await pick_diverse_articles(db, n=NUM_BIAS_ARTICLES)
        stories = await pick_stories_with_articles(db, n=NUM_SUMMARY_STORIES)

    if not articles:
        print("ERROR: No articles with content found in DB.")
        return
    if not stories:
        print("WARN: No stories with ≥3 articles found — skipping summary comparison.")

    logger.info(f"Running bias scoring across {len(MODELS)} models on {len(articles)} articles...")
    bias_blocks = await compare_bias(client, articles)

    summary_blocks = []
    if stories:
        logger.info(f"Running summary comparison across {len(MODELS)} models on {len(stories)} stories...")
        summary_blocks = await compare_summary(client, stories)

    # Write the report
    header = [
        f"# Doornegar Model Comparison — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"Comparing: {', '.join(MODELS)}\n",
        "## How to read this file",
        "",
        "- **Bias scoring section**: each article is shown with all 4 models' ratings side-by-side. Check whether cheaper models agree with `gpt-4o-mini` (the current baseline). Large disagreements = quality loss.",
        "- **Summary section**: each story is shown with all 4 models' Persian summaries. Read them as a native speaker and judge which feels most accurate, coherent, and useful.",
        "- **Your decision**: if a cheaper model produces outputs you'd accept as a human reader, it's a safe switch. If it misclassifies obviously biased state media as neutral, **don't** switch that step.",
        "",
    ]
    report = "\n".join(header + bias_blocks + summary_blocks)
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    logger.info(f"Wrote {OUTPUT_FILE}")
    print(f"\n✅ Done. Open the file in your editor:\n   {OUTPUT_FILE}\n")


if __name__ == "__main__":
    asyncio.run(main())

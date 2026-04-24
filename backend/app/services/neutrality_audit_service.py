"""Claude-scored neutrality audit — run-it-all server-side variant.

Wraps the same logic as scripts/neutrality_audit.py (export → Claude →
apply) into a single callable so an admin endpoint can run the full
loop without shuffling JSON through a human.

Design:
  1. Load top-N trending stories that don't already carry neutrality
     scores (matches the script's filter). Oversample 3x so we can
     still land N after skipping already-scored ones.
  2. For each story, send its articles to Claude in one call and ask
     for per-article neutrality in the range -1 (heavy state framing)
     to +1 (heavy diaspora/opposition framing), with 0 as neutral.
  3. Aggregate per-article scores to per-source means and write both
     back into each story's summary_en blob — same shape the script
     produces, so the /stories/{id} page renders the political
     spectrum without any frontend changes.

Cost logged under purpose='neutrality_audit' in llm_usage_logs.

Per memory rule: external-API wrappers return None on failure. A
story whose Claude call fails is SKIPPED — we never write a zero
or guessed score into the DB.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.story import Story
from app.services.llm_usage import log_llm_usage
from app.services.narrative_groups import narrative_group as _narrative_group
from app.services.story_analysis import _compute_article_evidence

logger = logging.getLogger(__name__)

# Per-article content cap sent to Claude. Mirrors the script's constant
# so scoring consistency across the script-driven and server-driven
# paths stays intact.
ARTICLE_CONTENT_CAP = 3000

# Claude model for neutrality scoring. Haiku is plenty for the judgment
# task and keeps the audit under $1-2 per full run.
SCORING_MODEL = "claude-haiku-4-5-20251001"

# Per-story LLM output cap. A JSON map of {article_id: float} for ~20
# articles easily fits in 1024 tokens.
MAX_OUTPUT_TOKENS = 1024


_SYSTEM_PROMPT = """\
You are a bias-neutrality rater for Iranian media coverage. Given a \
story and its articles from different Persian-language outlets, assign \
each article a neutrality score on a continuous scale from -1.0 to +1.0:

  -1.0  heavy state-aligned / pro-regime framing
   0.0  neutral, fact-forward, minimal loaded language
  +1.0  heavy diaspora-opposition / anti-regime framing

Score the ARTICLE's framing, not the outlet's usual stance — an \
inside-Iran outlet can still publish a 0 on a given piece, and a \
diaspora outlet can still drop below +0.3 on something straightforward.

Anchor points in the Iranian context:
  -0.7 to -1.0: uses شهادت / فتنه / اغتشاشگر / ضدانقلاب; frames \
    protests as foreign-organized; celebrates سپاه / رهبر; presents \
    western sanctions as unjustified economic war
  -0.3 to -0.6: echoes state framing without extreme loaded terms; \
    under-reports domestic problems
  -0.2 to +0.2: multiple viewpoints, factual register, uses neutral \
    terms like معترضان / درگیری / اقتصاد
   +0.3 to +0.6: highlights victims / prisoners / economic collapse \
    with moderation; critical of regime but evidence-based
   +0.7 to +1.0: uses قیام / سرکوبگر / کشتار / اعدام heavily; frames \
    the regime as illegitimate; celebrates diaspora figures

Output STRICT JSON only. No markdown fences. The shape is:
{
  "article_neutrality": {
    "<article_id>": -0.4,
    "<article_id>": 0.1,
    ...
  }
}
Keys must be the exact article_id UUIDs from the input. Values must \
be floats in [-1.0, 1.0]. Every article in the input must receive a \
score — no omissions.\
"""


def _build_story_prompt(story_payload: dict) -> str:
    """Compact input for one Claude call. Keeps per-article content
    trimmed to ARTICLE_CONTENT_CAP chars (the script's rule)."""
    arts_brief = []
    for a in story_payload["articles"]:
        arts_brief.append({
            "article_id": a["id"],
            "source_slug": a["source_slug"],
            "subgroup": a["narrative_group"],
            "title": a["title"][:300],
            "content": a["content"][:ARTICLE_CONTENT_CAP],
        })
    payload = {
        "story_id": story_payload["story_id"],
        "story_title_fa": story_payload.get("title_fa"),
        "articles": arts_brief,
    }
    return (
        "Score each article's neutrality. Return the JSON map described "
        "in the system prompt, one entry per article_id.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _parse_scores(text: str) -> dict[str, float] | None:
    s = text.strip()
    if "```json" in s:
        s = s.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in s:
        s = s.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.warning(f"neutrality_audit: JSON parse failed: {e} | head={text[:200]!r}")
        return None
    if not isinstance(parsed, dict):
        return None
    scores_raw = parsed.get("article_neutrality")
    if not isinstance(scores_raw, dict):
        return None
    out: dict[str, float] = {}
    for k, v in scores_raw.items():
        try:
            val = float(v)
            out[str(k)] = max(-1.0, min(1.0, val))
        except (TypeError, ValueError):
            continue
    return out or None


async def _score_story(story_payload: dict) -> tuple[dict[str, float] | None, dict]:
    """Call Claude once for this story. Returns (scores, usage_dict).

    On failure returns (None, {}) — NEVER a zero-default map. Per the
    no-silent-fallbacks rule, the caller skips this story instead of
    writing a guessed score.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured for neutrality audit")

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    msg = await client.messages.create(
        model=SCORING_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_story_prompt(story_payload)}],
    )
    text = msg.content[0].text if msg.content else ""
    usage = {
        "input_tokens": getattr(msg.usage, "input_tokens", 0),
        "output_tokens": getattr(msg.usage, "output_tokens", 0),
    }
    await log_llm_usage(
        model=SCORING_MODEL,
        purpose="neutrality_audit",
        usage=usage,
        story_id=story_payload["story_id"],
    )
    scores = _parse_scores(text)
    if scores is None:
        logger.warning(
            f"neutrality_audit: no valid scores returned for story "
            f"{story_payload['story_id']}"
        )
    return scores, usage


async def _load_candidate_stories(
    db: AsyncSession, top_n: int, include_scored: bool,
) -> list[dict]:
    """Mirror scripts/neutrality_audit.py::export but return in-memory."""
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.summary_fa.isnot(None))
        .order_by(Story.trending_score.desc())
        .limit(top_n * 3)  # oversample so skips don't starve us
    )
    stories = list(result.scalars().all())

    picked: list[dict] = []
    for s in stories:
        try:
            blob = json.loads(s.summary_en) if s.summary_en else {}
        except Exception:
            blob = {}
        if not include_scored and isinstance(blob, dict) and blob.get("article_neutrality"):
            continue

        arts_out = []
        for a in s.articles:
            if not a.source:
                continue
            art_dict = {
                "title": a.title_original or a.title_fa or a.title_en or "",
                "content": (a.content_text or a.summary or "")[:ARTICLE_CONTENT_CAP],
            }
            evidence = _compute_article_evidence(art_dict)
            group = _narrative_group(a.source)
            arts_out.append({
                "id": str(a.id),
                "source_slug": a.source.slug,
                "source_name_fa": a.source.name_fa,
                "narrative_group": group,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "title": art_dict["title"],
                "content": art_dict["content"],
                "evidence": evidence,
            })
        if not arts_out:
            continue
        picked.append({
            "story_id": str(s.id),
            "title_fa": s.title_fa,
            "article_count": len(arts_out),
            "articles": arts_out,
        })
        if len(picked) >= top_n:
            break
    return picked


async def _apply_scores(
    db: AsyncSession, story_id: str, article_scores: dict[str, float],
) -> bool:
    """Write scores into one story's summary_en blob. Same shape as the
    script so /stories/{id} rendering stays unchanged. Returns True
    iff we actually wrote something."""
    res = await db.execute(
        select(Story)
        .options(selectinload(Story.articles).selectinload(Article.source))
        .where(Story.id == story_id)
    )
    story = res.scalar_one_or_none()
    if not story:
        return False

    per_source: dict[str, list[float]] = {}
    for a in story.articles:
        score = article_scores.get(str(a.id))
        if score is None or not a.source:
            continue
        per_source.setdefault(a.source.slug, []).append(score)
    if not per_source:
        return False
    source_neutrality = {slug: sum(v) / len(v) for slug, v in per_source.items()}

    try:
        blob = json.loads(story.summary_en) if story.summary_en else {}
    except Exception:
        blob = {}
    if not isinstance(blob, dict):
        blob = {}

    blob["article_neutrality"] = article_scores
    blob["source_neutrality"] = source_neutrality
    blob["neutrality_source"] = "claude"
    blob["neutrality_scored_at"] = datetime.now(timezone.utc).isoformat()
    story.summary_en = json.dumps(blob, ensure_ascii=False)
    return True


async def run_neutrality_audit(
    db: AsyncSession,
    top_n: int = 30,
    include_scored: bool = False,
) -> dict[str, Any]:
    """Full loop: pick top-N → score each with Claude → write back.

    Returns a stats dict for the admin response / maintenance log.
    """
    stories = await _load_candidate_stories(db, top_n, include_scored)
    if not stories:
        logger.info("neutrality_audit: no candidate stories")
        return {
            "candidates": 0, "scored": 0, "skipped": 0,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        }

    logger.info(f"neutrality_audit: scoring {len(stories)} stories")
    scored = 0
    skipped = 0
    total_in = 0
    total_out = 0

    for payload in stories:
        try:
            scores, usage = await _score_story(payload)
            total_in += usage.get("input_tokens", 0)
            total_out += usage.get("output_tokens", 0)
            if not scores:
                skipped += 1
                continue
            wrote = await _apply_scores(db, payload["story_id"], scores)
            if wrote:
                scored += 1
            else:
                skipped += 1
        except Exception:
            logger.exception(
                f"neutrality_audit: failed for story {payload['story_id']}"
            )
            skipped += 1

    await db.commit()
    # Haiku pricing: $0.80/1M input, $4.00/1M output.
    cost_usd = round((total_in * 0.80 + total_out * 4.00) / 1_000_000, 5)
    return {
        "candidates": len(stories),
        "scored": scored,
        "skipped": skipped,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": cost_usd,
    }

"""LLM-based bias scoring service.

Analyzes articles for political alignment, framing, tone, factuality,
and emotional language using structured LLM prompts. Designed for the
Iranian media context with dimensions specific to state/diaspora dynamics.

Supports both Anthropic (Claude) and OpenAI (GPT) as LLM backends.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.article import Article
from app.models.bias_score import BiasScore

logger = logging.getLogger(__name__)

# Iranian-context framing labels
FRAMING_LABELS = [
    "conflict",
    "human_interest",
    "economic_impact",
    "morality",
    "responsibility",
    "security",
    "victimization",
    "resistance",
    "sovereignty",
    "western_interference",
    "human_rights",
    "reform",
    "stability",
    "national_pride",
    "corruption",
]

BIAS_ANALYSIS_PROMPT = """\
You are a media bias analyst specializing in Iranian news media. You understand \
the dynamics between state-controlled media (inside Iran), diaspora/opposition media \
(outside Iran), and independent outlets.

Analyze the following news article and provide bias ratings. The source of the \
article is HIDDEN — do not try to guess it. Analyze only based on the text content.

ARTICLE:
Title: {title}
Text: {text}

Rate the following dimensions. You MUST return valid JSON only, no other text.

{{
  "political_alignment": <float, -1.0 (strongly pro-Islamic Republic establishment) to +1.0 (strongly anti-establishment / opposition)>,
  "pro_regime_score": <float, 0.0-1.0, how favorable to IR government/supreme leader>,
  "reformist_score": <float, 0.0-1.0, alignment with reformist movement>,
  "opposition_score": <float, 0.0-1.0, alignment with opposition/diaspora movements>,
  "framing_labels": <list of strings from: {framing_labels}>,
  "tone_score": <float, -1.0 (very negative/alarming) to +1.0 (very positive/celebratory)>,
  "emotional_language_score": <float, 0.0 (purely factual, neutral language) to 1.0 (heavily emotional, loaded words, propaganda-like)>,
  "factuality_score": <float, 0.0 (pure opinion/propaganda) to 1.0 (thoroughly sourced, verifiable facts)>,
  "source_citation_count": <int, number of named/identified sources cited in the article>,
  "anonymous_source_count": <int, number of unnamed/anonymous sources>,
  "uses_loaded_language": <bool, true if article uses emotionally charged or propaganda-like language>,
  "reasoning_en": "<2-3 sentences explaining your ratings in English>",
  "reasoning_fa": "<2-3 sentences explaining your ratings in Persian/Farsi>"
}}

Guidelines for Iranian media context:
- State media often frames sanctions as "economic war", protests as "riots/sedition", and opposition as "enemies"
- Diaspora media may frame protests as "uprisings", government actions as "repression", and sanctions as justified
- Look for loaded terms: فتنه (sedition), اغتشاشگر (rioter), مبارز (fighter/activist), شهید (martyr)
- Factual articles cite specific sources, data, and allow multiple viewpoints
- Propaganda tends to use absolute language, emotional appeals, and one-sided framing
"""


async def score_article_bias(
    article: Article, db: AsyncSession
) -> BiasScore | None:
    """Score a single article's bias using an LLM.

    Returns the created BiasScore or None if scoring fails.
    """
    text = article.content_text or article.summary or ""
    if not text and not article.title_original:
        logger.warning(f"Article {article.id} has no text to analyze")
        return None

    # Truncate text to ~2000 tokens (roughly 8000 chars for Persian)
    text = text[:8000]

    prompt = BIAS_ANALYSIS_PROMPT.format(
        title=article.title_original,
        text=text,
        framing_labels=json.dumps(FRAMING_LABELS),
    )

    try:
        response_text = await _call_llm(prompt)
        scores = _parse_llm_response(response_text)
        if scores is None:
            return None

        bias_score = BiasScore(
            article_id=article.id,
            political_alignment=scores.get("political_alignment"),
            pro_regime_score=scores.get("pro_regime_score"),
            reformist_score=scores.get("reformist_score"),
            opposition_score=scores.get("opposition_score"),
            framing_labels=scores.get("framing_labels", []),
            tone_score=scores.get("tone_score"),
            emotional_language_score=scores.get("emotional_language_score"),
            factuality_score=scores.get("factuality_score"),
            source_citation_count=scores.get("source_citation_count"),
            anonymous_source_count=scores.get("anonymous_source_count"),
            uses_loaded_language=scores.get("uses_loaded_language"),
            scoring_method="llm_initial",
            llm_model=settings.bias_scoring_model,
            confidence=_estimate_confidence(scores),
            reasoning_en=scores.get("reasoning_en"),
            reasoning_fa=scores.get("reasoning_fa"),
        )
        db.add(bias_score)
        return bias_score

    except Exception as e:
        logger.error(f"Failed to score article {article.id}: {e}")
        return None


async def score_unscored_articles(db: AsyncSession, batch_size: int = 20) -> dict:
    """Score all articles that don't have bias scores yet.

    Returns stats: {scored, failed, skipped}.
    """
    # Find articles without bias scores
    scored_article_ids = select(BiasScore.article_id).distinct()
    result = await db.execute(
        select(Article)
        .where(
            Article.id.notin_(scored_article_ids),
            Article.story_id.isnot(None),  # Only score articles in stories
        )
        .limit(batch_size)
    )
    articles = result.scalars().all()

    stats = {"scored": 0, "failed": 0, "skipped": 0}

    for article in articles:
        if not article.content_text and not article.summary:
            stats["skipped"] += 1
            continue

        bias_score = await score_article_bias(article, db)
        if bias_score:
            stats["scored"] += 1
        else:
            stats["failed"] += 1

    await db.commit()
    logger.info(f"Bias scoring complete: {stats}")
    return stats


async def _call_llm(prompt: str) -> str:
    """Call the configured LLM and return the response text.

    Tries OpenAI first (more reliable), falls back to Anthropic.
    """
    if settings.openai_api_key:
        return await _call_openai(prompt)
    elif settings.anthropic_api_key:
        return await _call_anthropic(prompt)
    else:
        raise RuntimeError(
            "No LLM API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )


async def _call_anthropic(prompt: str) -> str:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.bias_scoring_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _call_openai(prompt: str) -> str:
    """Call OpenAI API."""
    import openai

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.3,
    )
    return response.choices[0].message.content


def _parse_llm_response(response_text: str) -> dict | None:
    """Parse JSON response from LLM, handling common formatting issues."""
    try:
        # Try to extract JSON from the response
        text = response_text.strip()

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        scores = json.loads(text)

        # Validate and clamp values
        if "political_alignment" in scores:
            scores["political_alignment"] = max(-1.0, min(1.0, float(scores["political_alignment"])))
        if "tone_score" in scores:
            scores["tone_score"] = max(-1.0, min(1.0, float(scores["tone_score"])))

        for field in ["pro_regime_score", "reformist_score", "opposition_score",
                       "emotional_language_score", "factuality_score"]:
            if field in scores:
                scores[field] = max(0.0, min(1.0, float(scores[field])))

        # Validate framing labels
        if "framing_labels" in scores:
            scores["framing_labels"] = [
                label for label in scores["framing_labels"]
                if label in FRAMING_LABELS
            ]

        return scores

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Failed to parse LLM response: {e}\nResponse: {response_text[:500]}")
        return None


def _estimate_confidence(scores: dict) -> float:
    """Estimate confidence based on completeness of the analysis."""
    required_fields = [
        "political_alignment", "tone_score", "factuality_score",
        "emotional_language_score",
    ]
    present = sum(1 for f in required_fields if scores.get(f) is not None)
    has_reasoning = bool(scores.get("reasoning_en"))
    has_framing = len(scores.get("framing_labels", [])) > 0

    completeness = present / len(required_fields)
    bonus = 0.1 if has_reasoning else 0
    bonus += 0.05 if has_framing else 0

    return min(1.0, completeness * 0.85 + bonus)

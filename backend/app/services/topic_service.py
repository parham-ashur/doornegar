"""Topic-based analysis service.

Handles topic creation, article matching, and LLM analysis generation
in both news and debate modes.
"""

import json
import logging
import re
import uuid

import openai
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.models.topic import Topic, TopicArticle

logger = logging.getLogger(__name__)

ALIGNMENT_LABELS_FA = {
    "state": "حکومتی",
    "semi_state": "نیمه‌حکومتی",
    "independent": "مستقل",
    "diaspora": "برون‌مرزی",
}


def _slugify(text: str) -> str:
    """Create a URL-safe slug from Farsi text."""
    slug = re.sub(r"[^\w\s-]", "", text.strip())
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")[:150]
    suffix = uuid.uuid4().hex[:6]
    return f"{slug}-{suffix}" if slug else suffix


async def create_topic(
    title_fa: str,
    db: AsyncSession,
    mode: str = "news",
    title_en: str | None = None,
    description_fa: str | None = None,
) -> Topic:
    """Create a new topic manually."""
    topic = Topic(
        title_fa=title_fa,
        title_en=title_en,
        slug=_slugify(title_fa),
        description_fa=description_fa,
        mode=mode,
        is_auto=False,
        created_by="admin",
    )
    db.add(topic)
    await db.flush()
    return topic


async def match_articles_to_topic(
    topic: Topic,
    db: AsyncSession,
    days: int = 7,
    limit: int = 50,
) -> int:
    """Find and link articles that match a topic using keyword search.

    Uses PostgreSQL full-text search on article titles and content
    against the topic title keywords.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Extract keywords from topic title (split on spaces, filter short words)
    keywords = [w for w in topic.title_fa.split() if len(w) > 2]
    if not keywords:
        return 0

    # Find articles matching any keyword in title or content
    query = (
        select(Article)
        .join(Source, Article.source_id == Source.id, isouter=True)
        .where(Article.published_at >= cutoff)
    )

    # Build keyword filter: title_fa or title_original contains any keyword
    from sqlalchemy import or_
    keyword_filters = []
    for kw in keywords:
        keyword_filters.append(Article.title_fa.ilike(f"%{kw}%"))
        keyword_filters.append(Article.title_original.ilike(f"%{kw}%"))
    query = query.where(or_(*keyword_filters))
    query = query.limit(limit)

    result = await db.execute(query)
    articles = result.scalars().all()

    # Get existing links to avoid duplicates
    existing = await db.execute(
        select(TopicArticle.article_id).where(TopicArticle.topic_id == topic.id)
    )
    existing_ids = {row[0] for row in existing}

    linked = 0
    for article in articles:
        if article.id in existing_ids:
            continue

        # Calculate confidence based on keyword match count
        title = (article.title_fa or "") + " " + (article.title_original or "")
        matches = sum(1 for kw in keywords if kw in title)
        confidence = min(matches / len(keywords), 1.0)

        ta = TopicArticle(
            topic_id=topic.id,
            article_id=article.id,
            match_confidence=confidence,
            match_method="keyword",
        )
        db.add(ta)
        linked += 1

    topic.article_count = len(existing_ids) + linked
    await db.flush()

    logger.info(f"Matched {linked} articles to topic '{topic.title_fa}'")
    return linked


# ─── LLM Analysis ────────────────────────────────────────────

NEWS_ANALYSIS_PROMPT = """\
تو تحلیلگر رسانه‌ای هستی. موضوع تحلیل: {topic_title}
{topic_description}

مقالات مرتبط:
{articles_block}

خروجی: فقط JSON. مختصر و دقیق بنویس.

{{
  "summary_fa": "خلاصه کلی موضوع در ۳-۴ جمله. فقط حقایق.",
  "state_summary_fa": "دیدگاه رسانه‌های حکومتی در ۲-۳ جمله. اگر موجود نیست: null",
  "diaspora_summary_fa": "دیدگاه رسانه‌های برون‌مرزی در ۲-۳ جمله. اگر موجود نیست: null",
  "independent_summary_fa": "دیدگاه مستقل در ۲-۳ جمله. اگر موجود نیست: null",
  "bias_explanation_fa": "مقایسه مختصر تفاوت چارچوب‌بندی بین طرف‌ها در ۲-۳ جمله.",
  "scores": {{
    "state": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["از این لیست: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["..."]}},
    "independent": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["..."]}}
  }}
}}

اگر دسته‌ای نیست، null بگذار. فقط JSON."""

DEBATE_ANALYSIS_PROMPT = """\
تو تحلیلگر سیاسی هستی. موضوع بحث: {topic_title}
{topic_description}

مقالات و منابع مرتبط:
{articles_block}

وظیفه: تحلیل مواضع مختلف درباره این موضوع. دیدگاه‌های موافق و مخالف را شناسایی کن.

خروجی: فقط JSON.

{{
  "topic_summary_fa": "خلاصه موضوع بحث در ۲-۳ جمله.",
  "positions": [
    {{
      "position_fa": "عنوان موضع (مثلاً: موافقان مذاکره)",
      "argument_fa": "استدلال اصلی این موضع در ۲-۳ جمله.",
      "supporting_sources": ["نام منابعی که این موضع را دارند"],
      "strength": 1تا5
    }}
  ],
  "key_disagreements_fa": ["نقطه اختلاف اول", "نقطه اختلاف دوم"],
  "conclusion_fa": "جمع‌بندی مختصر: کجا توافق و کجا اختلاف وجود دارد؟"
}}

حداقل ۲ و حداکثر ۵ موضع شناسایی کن. فقط JSON."""


async def generate_topic_analysis(
    topic: Topic,
    articles_with_sources: list[dict],
) -> dict:
    """Generate LLM analysis for a topic."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    # Build articles block
    lines = []
    for i, art in enumerate(articles_with_sources, 1):
        alignment_fa = ALIGNMENT_LABELS_FA.get(art.get("state_alignment", ""), "نامشخص")
        lines.append(f"--- مقاله {i} ---")
        lines.append(f"عنوان: {art.get('title', 'بدون عنوان')}")
        lines.append(f"منبع: {art.get('source_name_fa', 'نامشخص')} (جهت‌گیری: {alignment_fa})")
        content = art.get("content", "")
        if content:
            lines.append(f"متن: {content}")
        lines.append("")

    articles_block = "\n".join(lines)
    description_line = f"\nتوضیحات: {topic.description_fa}" if topic.description_fa else ""

    if topic.mode == "debate":
        prompt = DEBATE_ANALYSIS_PROMPT.format(
            topic_title=topic.title_fa,
            topic_description=description_line,
            articles_block=articles_block,
        )
    else:
        prompt = NEWS_ANALYSIS_PROMPT.format(
            topic_title=topic.title_fa,
            topic_description=description_line,
            articles_block=articles_block,
        )

    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        from app.services.llm_usage import log_llm_usage
        await log_llm_usage(
            model="gpt-4o-mini",
            purpose="topic.analysis",
            usage=response.usage,
        )
        response_text = response.choices[0].message.content
        return _parse_response(response_text)

    except openai.APIError as e:
        logger.error(f"OpenAI API error for topic {topic.id}: {e}")
        raise RuntimeError(f"OpenAI API call failed: {e}")


ANALYST_PROMPT = """\
تو باید نقش ۱۰ تا ۱۵ تحلیلگر سیاسی ایرانی مختلف را بازی کنی. موضوع: {topic_title}

خلاصه موضوع: {topic_summary}

برای هر تحلیلگر یک نام واقع‌گرایانه فارسی، پلتفرم، تعداد دنبال‌کننده، گرایش سیاسی، و یک نقل‌قول ۱-۲ جمله‌ای بنویس.

ترکیب گرایش‌ها:
- ۲-۳ نزدیک به حکومت (pro_regime)
- ۲-۳ اصلاح‌طلب (reformist)
- ۲-۳ اپوزیسیون (opposition)
- ۱-۲ آکادمیک/بی‌طرف (neutral)
- ۱-۲ سلطنت‌طلب (monarchist)

خروجی: فقط JSON.

{{
  "analysts": [
    {{
      "name_fa": "نام فارسی",
      "platform": "twitter یا telegram",
      "followers": "مثلاً 120K یا 45K",
      "political_leaning": "pro_regime/reformist/opposition/neutral/monarchist",
      "quote_fa": "نقل‌قول ۱-۲ جمله‌ای درباره موضوع"
    }}
  ]
}}

فقط JSON. نام‌ها باید واقع‌گرایانه باشند اما ساختگی."""


async def generate_analyst_perspectives(
    topic: Topic,
    topic_summary: str,
) -> list[dict]:
    """Generate mock analyst perspectives using LLM."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    prompt = ANALYST_PROMPT.format(
        topic_title=topic.title_fa,
        topic_summary=topic_summary or topic.title_fa,
    )

    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
        )
        from app.services.llm_usage import log_llm_usage
        await log_llm_usage(
            model="gpt-4o-mini",
            purpose="topic.analysts",
            usage=response.usage,
        )
        result = _parse_response(response.choices[0].message.content)
        return result.get("analysts", [])
    except openai.APIError as e:
        logger.error(f"OpenAI API error generating analysts for topic {topic.id}: {e}")
        raise RuntimeError(f"OpenAI API call failed: {e}")


def _parse_response(response_text: str) -> dict:
    """Parse JSON response from LLM."""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse topic analysis: {e}\nResponse: {response_text[:500]}")
        raise RuntimeError("Failed to parse LLM response as JSON")

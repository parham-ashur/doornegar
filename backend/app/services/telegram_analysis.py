"""Deep two-pass LLM analysis of Telegram discourse around a story.

Pass 1 (nano): Extract structured facts from posts — who said what, key claims, numbers
Pass 2 (premium): Deep framing analysis with cross-story context and channel track records

Same "human approach" as article analysis: read facts first, then analyze patterns.
"""

import json
import logging

import openai
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.social import TelegramChannel, TelegramPost
from app.models.story import Story

logger = logging.getLogger(__name__)

# ── Channel track records (historical reliability patterns) ──
CHANNEL_TRACK_RECORDS = {
    "pro_regime": "کانال‌های حکومتی معمولاً: ارقام تلفات خودی را کمتر، دستاوردها را بزرگ‌تر نشان می‌دهند. از واژه «شهید» و «پیروزی» زیاد استفاده می‌کنند. اخبار منفی داخلی را سانسور یا تأخیر می‌اندازند.",
    "opposition": "کانال‌های اپوزیسیون معمولاً: ارقام تلفات را بالاتر، بحران‌ها را بزرگ‌تر نشان می‌دهند. از واژه‌های احساسی و تحریک‌آمیز استفاده می‌کنند. موفقیت‌های دولت را نادیده می‌گیرند.",
    "reformist": "کانال‌های اصلاح‌طلب معمولاً: نقد درون‌سیستمی دارند. بین حمایت و انتقاد نوسان می‌کنند. اطلاعات نسبتاً دقیق‌تری ارائه می‌دهند.",
    "neutral": "کانال‌های مستقل: معمولاً چند منبع را مقایسه می‌کنند. از زبان احتیاطی استفاده می‌کنند.",
}

# ── Pass 1: Fact extraction (cheap, nano model) ──
PASS1_PROMPT = """از پست‌های تلگرامی زیر، حقایق ساختاریافته استخراج کن.

═══ پست‌ها ═══
{posts_block}
═══ پایان ═══

JSON برگردان:
{{
  "facts": [
    {{"channel": "نام کانال", "leaning": "گرایش", "claim": "ادعای اصلی", "numbers": "ارقام اگر موجود", "tone": "لحن: خشم/امید/ترس/خنثی"}},
    ...
  ],
  "common_themes": ["موضوع مشترک ۱", "موضوع مشترک ۲"],
  "contradictions": ["تناقض ۱ بین کانال‌ها", "تناقض ۲"]
}}

فقط JSON."""

# ── Pass 2: Deep analysis (premium model with context) ──
PASS2_PROMPT = """تو یک تحلیلگر ارشد رسانه‌ای هستی. حقایق استخراج‌شده از پست‌های تلگرامی درباره یک موضوع خبری را تحلیل کن.

عنوان: {story_title}
خلاصه خبری: {story_summary}

═══ حقایق استخراج‌شده (پاس اول) ═══
{facts_json}

═══ سابقه کانال‌ها ═══
{track_records}

═══ حافظه بین‌موضوعی ═══
{cross_story_context}

═══ پست‌های خام (نمونه) ═══
{sample_posts}

# دستورالعمل تحلیل

مثل یک تحلیلگر باتجربه فکر کن:
- ادعاهای هر طرف را با سابقه آن کانال مقایسه کن
- به ارقام و اعداد توجه ویژه کن: آیا منطقی هستند؟ آیا طرف‌ها ارقام متفاوتی دارند؟
- الگوهای تکراری بین کانال‌ها را شناسایی کن (پیام هماهنگ؟)
- آنچه هیچ طرفی نگفته مهم‌تر از آنچه گفته‌اند است

# قوانین نگارشی مهم:
- کل متن فارسی باشد. هرگز از کلمات انگلیسی مثل opposition، pro-regime، escalating استفاده نکن
- از ضمیر «این» بدون مرجع مشخص استفاده نکن. مثلاً به جای «این تفاوت‌ها» بنویس «تفاوت روایت‌ها»
- هرگز با عبارات «فضای تلگرامی»، «گفتمان تلگرامی»، «تحلیل نشان می‌دهد» شروع نکن
- مستقیم وارد تحلیل شو، بدون مقدمه

JSON برگردان:
{{
  "discourse_summary": "۳-۴ جمله تحلیلی. مستقیم بنویس چرا هر طرف چنین موضعی دارد. بدون مقدمه یا عبارات کلیشه‌ای",
  "predictions": [
    {{"text": "پیش‌بینی مشخص بدون «با توجه به» — مستقیم بگو چه اتفاقی خواهد افتاد", "supporters": ["نام کانال‌هایی که مشابه پیش‌بینی کردند"], "pct": 40}},
    {{"text": "پیش‌بینی دوم", "supporters": ["کانال ۱", "کانال ۲"], "pct": 25}}
  ],
  "worldviews": {{
    "pro_regime": "روایت محافظه‌کار: چه می‌گویند و چرا (با نقل واژگان خاص)",
    "opposition": "روایت اپوزیسیون: چه می‌گویند و چرا (با نقل واژگان خاص)",
    "neutral": "دیدگاه مستقل‌ها (اگر موجود)"
  }},
  "key_claims": [
    "موضوع: [نام موضوع واحد] | ادعای مشخص + نام کانال + ارزیابی اعتبار. مثلاً: «موضوع: تعداد موشک‌های شلیک‌شده | کانال مصاف ادعا کرد ۵۰۰ موشک شلیک شده — مشکوک، زیرا منابع نظامی مستقل رقم کمتری تأیید کردند»",
    "ادعای دوم با همان موضوع یا موضوع جدید. اگر دو ادعا دربارهٔ یک موضوع واحد هستند، هر دو را بیاور تا خواننده مقایسه کند"
  ],
  "number_battle": "فقط وقتی دو یا چند کانال دربارهٔ یک موضوع واحد (مثلاً «تعداد تلفات حملهٔ ۱۳ آوریل») ارقام متفاوت می‌دهند: ابتدا موضوع مشترک را نام ببر، سپس ارقام متفاوت و منابع آنها را بنویس. اگر کانال‌ها دربارهٔ موضوعات مختلف عدد می‌دهند (مثلاً یکی «مدت آتش‌بس» و دیگری «مدت جنگ»)، آنها را مقایسه نکن — null بگذار",
  "coordinated_messaging": "آیا چند کانال دقیقاً یک متن/پیام را منتشر کردند؟ الگوی هماهنگی؟",
  "consensus": "نقاط توافق و اختلاف — چه چیزی همه قبول دارند؟",
  "missing_voices": "صداهای غایب: چه کسی حرف نزده؟ چه موضوعی سانسور شده؟",
  "reliability_note": "با توجه به سابقه کانال‌ها، کدام روایت قابل‌اعتمادتر است؟"
}}

فقط JSON. بدون فیلد emotional_tone."""


async def _pass1_extract_facts(posts_block: str) -> dict | None:
    """Pass 1: Extract structured facts from posts using nano model."""
    prompt = PASS1_PROMPT.format(posts_block=posts_block)
    try:
        from app.services.llm_helper import build_openai_params
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        params = build_openai_params(
            model=settings.translation_model,  # nano
            prompt=prompt,
            max_tokens=2048,
            temperature=0,
        )
        response = await client.chat.completions.create(**params)
        text = response.choices[0].message.content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Pass 1 telegram fact extraction failed: {e}")
        return None


async def _get_cross_story_context(db: AsyncSession, story_id: str) -> str:
    """Get summaries of related stories for cross-story memory."""
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story or not story.centroid_embedding:
        return "حافظه بین‌موضوعی: ندارد"

    from app.nlp.embeddings import cosine_similarity

    # Find similar stories
    result = await db.execute(
        select(Story).where(
            Story.id != story_id,
            Story.centroid_embedding.isnot(None),
            Story.summary_fa.isnot(None),
        ).limit(100)
    )
    candidates = result.scalars().all()

    related = []
    for s in candidates:
        c = s.centroid_embedding
        if not isinstance(c, list) or not c or any(v is None for v in c):
            continue
        try:
            sim = cosine_similarity(story.centroid_embedding, c)
        except (TypeError, ValueError):
            continue
        if sim > 0.5:
            related.append((sim, s))

    related.sort(key=lambda x: -x[0])
    if not related:
        return "حافظه بین‌موضوعی: موضوع مشابهی یافت نشد"

    lines = ["موضوعات مرتبط:"]
    for sim, s in related[:3]:
        lines.append(f"- {s.title_fa}: {(s.summary_fa or '')[:100]}")
    return "\n".join(lines)


def _build_track_records(posts: list) -> str:
    """Build channel track records based on leanings present in posts."""
    leanings_seen = set()
    for p in posts:
        if p.channel and p.channel.political_leaning:
            leanings_seen.add(p.channel.political_leaning)

    lines = []
    for leaning in leanings_seen:
        if leaning in CHANNEL_TRACK_RECORDS:
            lines.append(f"[{leaning}] {CHANNEL_TRACK_RECORDS[leaning]}")
    return "\n".join(lines) if lines else "سابقه‌ای ثبت نشده"


async def analyze_story_telegram(
    db: AsyncSession,
    story_id: str,
) -> dict | None:
    """Two-pass deep analysis of Telegram discourse for a story.

    Pass 1 (nano): Extract facts, themes, contradictions
    Pass 2 (premium): Deep analysis with cross-story context + channel track records
    """
    if not settings.openai_api_key:
        return None

    # Fetch story
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story:
        return None

    # Fetch posts from NON-MEDIA channels only (analysts, commentators, aggregators)
    # Media channel posts are used for article bias comparison instead
    posts_result = await db.execute(
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .join(TelegramChannel, TelegramPost.channel_id == TelegramChannel.id)
        .where(TelegramPost.story_id == story_id)
        .where(TelegramPost.text.isnot(None))
        .where(TelegramPost.text != "")
        .where(TelegramChannel.channel_type.in_(["commentary", "aggregator", "activist", "political_party", "citizen"]))
        .order_by(TelegramPost.date.desc())
        .limit(40)
    )
    posts = list(posts_result.scalars().all())

    # If not enough non-media posts, fall back to all posts
    if len(posts) < 2:
        posts_result = await db.execute(
            select(TelegramPost)
            .options(selectinload(TelegramPost.channel))
            .where(TelegramPost.story_id == story_id)
            .where(TelegramPost.text.isnot(None))
            .where(TelegramPost.text != "")
            .order_by(TelegramPost.date.desc())
            .limit(40)
        )
        posts = list(posts_result.scalars().all())

    if len(posts) < 2:
        return None

    # Build posts block
    lines = []
    for p in posts:
        channel_name = p.channel.title if p.channel else "ناشناس"
        leaning = p.channel.political_leaning if p.channel else "unknown"
        text = (p.text or "")[:400]
        views = p.views or 0
        lines.append(f"کانال: {channel_name} (گرایش: {leaning}, بازدید: {views})")
        lines.append(f"متن: {text}")
        lines.append("")
    posts_block = "\n".join(lines)

    # ── Pass 1: Extract facts (nano, cheap) ──
    facts_data = await _pass1_extract_facts(posts_block)
    facts_json = json.dumps(facts_data, ensure_ascii=False, indent=2) if facts_data else "استخراج حقایق ناموفق بود"

    # ── Context: cross-story memory + track records ──
    cross_context = await _get_cross_story_context(db, story_id)
    track_records = _build_track_records(posts)

    # Sample posts for pass 2 (top 10 by views)
    sorted_posts = sorted(posts, key=lambda p: p.views or 0, reverse=True)[:10]
    sample_lines = []
    for p in sorted_posts:
        ch = p.channel.title if p.channel else "?"
        sample_lines.append(f"[{ch}] {(p.text or '')[:200]}")
    sample_posts = "\n\n".join(sample_lines)

    # ── Pass 2: Deep analysis (premium model) ──
    prompt = PASS2_PROMPT.format(
        story_title=story.title_fa or story.title_en or "",
        story_summary=story.summary_fa or story.summary_en or "خلاصه‌ای موجود نیست",
        facts_json=facts_json,
        track_records=track_records,
        cross_story_context=cross_context,
        sample_posts=sample_posts,
    )

    try:
        from app.services.llm_helper import build_openai_params

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        # Use baseline model for pass 2 (better quality)
        model = getattr(settings, "baseline_model", None) or settings.translation_model
        params = build_openai_params(
            model=model,
            prompt=prompt,
            max_tokens=3000,
            temperature=0.2,
        )
        response = await client.chat.completions.create(**params)
        text = response.choices[0].message.content.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        # Normalize key_claims to strings for frontend compatibility
        if "key_claims" in result and result["key_claims"]:
            normalized_claims = []
            for c in result["key_claims"]:
                if isinstance(c, dict):
                    claim_text = c.get("claim", "")
                    source = c.get("source", "")
                    cred = c.get("credibility", "")
                    normalized_claims.append(f"{claim_text} ({source} — {cred})")
                else:
                    normalized_claims.append(str(c))
            result["key_claims"] = normalized_claims

        return result

    except Exception as e:
        logger.warning(f"Telegram analysis pass 2 failed for story {story_id}: {e}")
        return None


async def link_posts_by_embedding(db: AsyncSession, threshold: float = 0.35) -> dict:
    """Link unlinked Telegram posts to stories via embedding similarity.

    Replaces URL-based matching with semantic matching.
    """
    from app.nlp.embeddings import generate_embeddings_batch, cosine_similarity

    # Load stories with centroids
    result = await db.execute(
        select(Story).where(
            Story.centroid_embedding.isnot(None),
            Story.article_count >= 3,
        )
    )
    stories = list(result.scalars().all())
    # Validate centroids — some rows have dicts, lists with None values, or
    # partially-initialized vectors from older code. Skip anything that
    # isn't a clean list of finite numbers so cosine_similarity can't raise
    # "unsupported operand type(s) for *: 'float' and 'NoneType'".
    story_data = []
    for s in stories:
        c = s.centroid_embedding
        if not isinstance(c, list) or len(c) == 0:
            continue
        if any(v is None or not isinstance(v, (int, float)) for v in c):
            continue
        story_data.append((str(s.id), c))

    if not story_data:
        return {"linked": 0, "reason": "no stories with centroids"}

    # Get unlinked posts
    result = await db.execute(
        select(TelegramPost).where(
            TelegramPost.story_id.is_(None),
            TelegramPost.text.isnot(None),
            TelegramPost.text != "",
        )
    )
    posts = list(result.scalars().all())

    if not posts:
        return {"linked": 0, "reason": "no unlinked posts"}

    # Embed posts
    post_texts = [(p.text or "")[:500] for p in posts]
    embeddings = generate_embeddings_batch(post_texts, batch_size=100)

    # Match
    from sqlalchemy import update
    linked = 0
    for post, emb in zip(posts, embeddings):
        if not emb or all(v == 0 for v in emb) or any(v is None for v in emb):
            continue

        best_score = 0
        best_story_id = None
        for story_id, centroid in story_data:
            try:
                score = cosine_similarity(emb, centroid)
            except Exception:
                # Defensive: any shape/type mismatch between emb and centroid
                # (dimension mismatch, null inside) should skip, not crash
                continue
            if score > best_score:
                best_score = score
                best_story_id = story_id

        if best_score >= threshold and best_story_id:
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.id == post.id)
                .values(story_id=best_story_id)
            )
            linked += 1

    await db.commit()
    logger.info(f"Embedding-linked {linked} telegram posts to stories")
    return {"linked": linked, "total_posts": len(posts), "threshold": threshold}

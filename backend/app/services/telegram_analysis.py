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

# ── Pass 0: Niloofar's editorial triage ──
# Upstream filter deciding which posts deserve analyst-level attention.
# Previously ran on nano with a short rule-based prompt that was too
# literal — it marked any post without hedging words («احتمالاً»، «فکر
# می‌کنم») as "news" even when the post made a substantive argument
# without those surface markers. Result: most sophisticated Persian
# commentary got dropped and stories fell below the 2-post threshold.
#
# Niloofar's voice asks the sharper question a real editor asks: "Would
# I cite this post as a source in a media column?" That catches
# analytical posts missing surface hedges, and still rejects headline
# rebroadcasts. Runs on the baseline tier (gpt-4o-mini) where nuanced
# Persian judgment actually pays off — nano was the false economy.
PASS0_CLASSIFY_PROMPT = """تو نیلوفر هستی، سردبیر ارشد خبری با ۲۰ سال تجربه در ایران و خاورمیانه. وظیفه‌ات تصمیم‌گیری درباره این است که هر پست تلگرامی زیر، چه ارزشی برای یک ستون تحلیلی دارد.

═══ موضوع ═══
{story_title}
{story_summary}

═══ پست‌ها ═══
{posts_block}
═══ پایان ═══

برای هر پست، سه سؤال از خودت بپرس:
1. آیا این پست به من یک زاویهٔ دید، استدلال، علت، پیامد، یا پیش‌بینی دربارهٔ این موضوع می‌دهد؟
2. آیا در یک ستون تحلیلی این پست را به عنوان منبع نقل می‌کنی؟
3. آیا اصلاً به این موضوع مشخص مربوط است؟

برچسب‌گذاری:

- "analysis" — پست تحلیل، استدلال، ارزیابی، علت‌یابی، پیش‌بینی، مقایسه، نقد، یا موضع‌گیری دارد. ممکن است واژه‌های محافظه‌کارانه («احتمالاً»، «فکر می‌کنم») نداشته باشد ولی استدلال روشنی ارائه کند. پست‌های کوتاه مبارزاتی که موضع می‌گیرند («این توافق شکست خواهد خورد چون…») هم analysis‌اند. تحلیلگران حرفه‌ای اغلب قاطع می‌نویسند؛ نبودِ هجینگ نشانهٔ نبودِ تحلیل نیست.

- "news" — فقط گزارش واقعه، بازنشر تیتر خبرگزاری، نقل قول از مقام رسمی بدون تفسیر پست‌کننده، فوریات (breaking news) بدون افزودن زاویه. اگر پست فقط «چه اتفاقی افتاد» را می‌گوید و نه «چرا/چه معنایی دارد»، news است.

- "unrelated" — پست درباره موضوع دیگری است. فقط وقتی از این برچسب استفاده کن که کاملاً بی‌ربط باشد — پست‌های مرتبط ولی حاشیه‌ای را analysis/news بگذار.

قاعده در موارد مشکوک: اگر پست حتی یک جمله تحلیلی اضافه کرده، analysis است. خطای false-negative (دست‌کم گرفتن تحلیل) بدتر از false-positive (اضافه‌گیری) است، چون فیلترهای بعدی خطاهای پذیرشی را اصلاح می‌کنند ولی پست‌های رد شده از چرخه خارج می‌شوند.

JSON برگردان — فقط یک آرایه از برچسب‌ها به ترتیب پست‌ها:
{{"labels": ["analysis", "news", "analysis", "unrelated", ...]}}

فقط JSON."""


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
PASS2_PROMPT = """تو سردبیر ارشد خبری هستی. پست‌های تلگرامی ورودی فقط از تحلیلگران و صاحب‌نظران سیاسی هستند (رسانه‌های خبری و بازنشر‌کنندگان تیتر حذف شده‌اند). هدف: جمع‌بندی تحلیل‌ها، پیش‌بینی‌ها و ادعاهای این تحلیلگران — نه روایت رسانه‌ای.

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
    {{"text": "پیش‌بینی مشخص دربارهٔ اتفاقِ آینده — نه دربارهٔ رفتار رسانه‌ها. ممنوع: «روایت‌های حکومتی X خواهند کرد»، «کانال‌های اپوزیسیون تأکید خواهند کرد»، «رسانه‌ها تلاش می‌کنند Y را پنهان کنند». پیش‌بینی باید دربارهٔ خودِ رویداد باشد (آتش‌بس می‌شکند، مذاکرات شکست می‌خورد، تلفات از N می‌گذرد)، نه دربارهٔ چگونگیِ گزارش آن. ارزیابیِ اعتبارِ رسانه‌ها برای «reliability_note» است، نه «predictions».", "supporters": ["نام کانال‌هایی که مشابه پیش‌بینی کردند"]}},
    {{"text": "پیش‌بینی دوم", "supporters": ["کانال ۱", "کانال ۲"]}}
  ],
  "worldviews": {{
    "pro_regime": "تحلیلگران نزدیک به دولت: چه می‌گویند و چرا (با نقل واژگان خاص)",
    "opposition": "تحلیلگران منتقد/اپوزیسیون: چه می‌گویند و چرا (با نقل واژگان خاص)",
    "neutral": "تحلیلگران مستقل/میانه‌رو (اگر موجود)"
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


async def _pass0_classify_posts(
    posts: list, story_title: str, story_summary: str
) -> list[str]:
    """Classify each post as analysis / news / unrelated in one batched call.

    Returns a label list aligned with `posts` (same length, same order).
    On LLM failure, returns ["analysis"] * len(posts) — fail-open so a
    nano outage doesn't kill the whole pipeline; downstream filters still
    apply via channel_type.
    """
    if not posts:
        return []
    if not settings.openai_api_key:
        return ["analysis"] * len(posts)

    lines = []
    for idx, p in enumerate(posts, start=1):
        ch = p.channel.title if p.channel else "?"
        text = (p.text or "")[:300]
        lines.append(f"[{idx}] [{ch}] {text}")
    posts_block = "\n\n".join(lines)

    try:
        from app.services.llm_helper import build_openai_params
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        # bias_scoring_model is the baseline tier (gpt-4o-mini). Nano was
        # too literal about Persian hedging markers and dropped real
        # analyst posts that happened to sound confident. Cost delta is
        # ~3× nano, but pass-0 runs on ≤60 posts per story × ≤15 top
        # stories per maintenance pass = ~$0.01/run — trivial at this
        # scale, and the accuracy win is what fills the sidebar.
        params = build_openai_params(
            model=settings.bias_scoring_model,
            prompt=PASS0_CLASSIFY_PROMPT.format(
                story_title=story_title or "",
                story_summary=(story_summary or "")[:300],
                posts_block=posts_block,
            ),
            max_tokens=512,
            temperature=0,
        )
        params["response_format"] = {"type": "json_object"}
        response = await client.chat.completions.create(**params)
        from app.services.llm_usage import log_llm_usage
        await log_llm_usage(
            model=settings.bias_scoring_model,
            purpose="telegram.pass0_classify",
            usage=response.usage,
            meta={"post_count": len(posts)},
        )
        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)
        labels = parsed.get("labels") or []
        if not isinstance(labels, list):
            return ["analysis"] * len(posts)
        # Pad or truncate to match posts length — the LLM occasionally
        # returns a short list if it got confused.
        if len(labels) < len(posts):
            labels = list(labels) + ["analysis"] * (len(posts) - len(labels))
        elif len(labels) > len(posts):
            labels = labels[:len(posts)]
        # Normalize unknown labels to "analysis" to stay fail-open.
        normalized = [
            lb if lb in ("analysis", "news", "unrelated") else "analysis"
            for lb in labels
        ]
        counts = {"analysis": 0, "news": 0, "unrelated": 0}
        for lb in normalized:
            counts[lb] += 1
        logger.info(
            f"Niloofar pass-0 triage ({len(posts)} posts): "
            f"{counts['analysis']} analysis, {counts['news']} news, {counts['unrelated']} unrelated"
        )
        return normalized
    except Exception as e:
        logger.warning(f"Niloofar pass-0 classifier failed, keeping all posts: {e}")
        return ["analysis"] * len(posts)


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
        from app.services.llm_usage import log_llm_usage
        await log_llm_usage(
            model=settings.translation_model,
            purpose="telegram.pass1_facts",
            usage=response.usage,
        )
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


def _normalize_channel_name(s: str) -> str:
    """Normalize Telegram channel/username strings for fuzzy matching.

    Lowercase, strip «@» + whitespace, collapse Arabic/Persian letter
    variants that the LLM's free-text supporter strings often vary on.
    """
    if not s:
        return ""
    t = s.strip().lower().replace("@", "").replace("«", "").replace("»", "")
    # ی / ي , ک / ك — keep Persian form
    t = t.replace("ي", "ی").replace("ك", "ک")
    # Strip "کانال " / "channel " prefix the LLM often adds
    for prefix in ("کانال ", "channel ", "@"):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t.strip()


async def enrich_predictions_with_analyst_counts(
    db: AsyncSession, analysis: dict
) -> dict:
    """Resolve each prediction's free-text `supporters` list to real analyst
    channels (commentary-typed, is_active) and compute
    `supporter_count` + `analysts_total` + a real `pct`.

    Replaces the old hallucinated `pct` (an LLM artifact — the prompt's
    JSON example had "pct": 40, which the model copied verbatim into
    every prediction). The numbers we write here are grounded in the
    TelegramChannel table, not invented by the LLM.

    Idempotent: safe to call on already-enriched analyses, and cheap
    (one DB query per story, O(supporters × analysts) in-memory match).
    """
    if not analysis or not isinstance(analysis, dict):
        return analysis

    preds = analysis.get("predictions") or []
    if not preds:
        return analysis

    # Load the universe of active analysts (commentary channels).
    # Filtered once per call — amortized over all predictions of the story.
    result = await db.execute(
        select(TelegramChannel).where(
            TelegramChannel.is_active.is_(True),
            TelegramChannel.channel_type == "commentary",
        )
    )
    analysts = list(result.scalars().all())
    total = len(analysts)

    if total == 0:
        return analysis

    # Lookup tables for cheap matching: exact username, exact title, and
    # a list for substring fallback (LLM often writes "کانال احمد زیدآبادی"
    # which contains the title but isn't equal to it).
    by_uname = {_normalize_channel_name(c.username): c for c in analysts if c.username}
    by_title = {_normalize_channel_name(c.title): c for c in analysts if c.title}
    titles_norm = [(c, _normalize_channel_name(c.title)) for c in analysts if c.title]

    def _match(name: str):
        n = _normalize_channel_name(name)
        if not n:
            return None
        if n in by_uname:
            return by_uname[n]
        if n in by_title:
            return by_title[n]
        # substring fallback, longest-first so "زیدآبادی" matches before a
        # generic two-letter partial.
        for c, t in sorted(titles_norm, key=lambda x: -len(x[1])):
            if t and (t in n or n in t):
                return c
        return None

    for pred in preds:
        if not isinstance(pred, dict):
            continue
        supporters = pred.get("supporters") or []
        matched_ids = set()
        for s in supporters:
            m = _match(s if isinstance(s, str) else str(s))
            if m is not None:
                matched_ids.add(m.id)
        count = len(matched_ids)
        pred["supporter_count"] = count
        pred["analysts_total"] = total
        pred["pct"] = round(count / total * 100) if total else 0

    return analysis


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
    is_premium: bool = True,
) -> dict | None:
    """Two-pass deep analysis of Telegram discourse for a story.

    Pass 1 (nano): Extract facts, themes, contradictions — skipped when
        fewer than 5 analyst posts survive pass-0 (Pass 2 can read them
        directly, facts extraction adds nothing at that scale).
    Pass 2 (gpt-4o-mini, both tiers): Deep analysis with cross-story
        context + channel track records. is_premium is still passed by
        the caller (top-5 vs #6-10) so the cost ledger keeps the tier
        breakdown, but both tiers now share the same cheaper model.
    """
    if not settings.openai_api_key:
        return None

    # Fetch story
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story:
        return None

    # Non-media pool: commentary + activist + citizen + political_party.
    # Aggregator was briefly included to widen the signal but Parham cut
    # it 2026-04-19 — aggregators rebroadcast headlines and leak news-
    # framing into the analyst narrative even through the pass-0 filter.
    # Keep state-media news channels out for the same reason; they feed
    # the article bias pipeline instead. Pass-0 below is still the hard
    # filter against news-rehash leaking in from the remaining types.
    ANALYTICAL_TYPES = ("commentary", "activist", "citizen", "political_party")
    posts_result = await db.execute(
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .join(TelegramChannel, TelegramPost.channel_id == TelegramChannel.id)
        .where(TelegramPost.story_id == story_id)
        .where(TelegramPost.text.isnot(None))
        .where(TelegramPost.text != "")
        .where(TelegramChannel.channel_type.in_(ANALYTICAL_TYPES))
        .where(TelegramChannel.is_active.is_(True))
        .order_by(TelegramPost.date.desc())
        .limit(60)
    )
    posts = list(posts_result.scalars().all())

    # Neighbor-story pool: the telegram linker writes each post to ONE
    # story_id (winner-takes-all by cosine score). Broad umbrella stories
    # (like the ceasefire+Hormuz hero, 175 articles) lose post after post
    # to narrower siblings that happen to match slightly better. Pull in
    # posts from stories whose centroid is highly similar to this one
    # — they're genuinely about the same topic, the linker just had to
    # pick a winner. Cap at NEIGHBOR_POST_BUDGET to keep pass-2 prompt
    # size in check. Only applies when the direct pool is thin.
    NEIGHBOR_CENTROID_THRESHOLD = 0.65
    NEIGHBOR_POST_BUDGET = 30
    DIRECT_POOL_FLOOR = 20  # skip neighbor borrow once the direct pool is rich
    if len(posts) < DIRECT_POOL_FLOOR and story.centroid_embedding:
        from app.nlp.embeddings import cosine_similarity as _cs
        own_centroid = story.centroid_embedding
        if isinstance(own_centroid, list) and all(
            isinstance(v, (int, float)) for v in own_centroid
        ):
            # Find neighbor stories by centroid similarity
            neighbors_result = await db.execute(
                select(Story).where(
                    Story.id != story.id,
                    Story.centroid_embedding.isnot(None),
                    Story.article_count >= 3,
                    Story.trending_score > 0,
                )
            )
            neighbor_ids: list[str] = []
            for neighbor in neighbors_result.scalars().all():
                c = neighbor.centroid_embedding
                if not isinstance(c, list) or not c:
                    continue
                if any(v is None or not isinstance(v, (int, float)) for v in c):
                    continue
                try:
                    sim = _cs(own_centroid, c)
                except Exception:
                    continue
                if sim >= NEIGHBOR_CENTROID_THRESHOLD:
                    neighbor_ids.append(str(neighbor.id))
            if neighbor_ids:
                have_ids = {str(p.id) for p in posts}
                borrow_result = await db.execute(
                    select(TelegramPost)
                    .options(selectinload(TelegramPost.channel))
                    .join(
                        TelegramChannel,
                        TelegramPost.channel_id == TelegramChannel.id,
                    )
                    .where(TelegramPost.story_id.in_(neighbor_ids))
                    .where(TelegramPost.text.isnot(None))
                    .where(TelegramPost.text != "")
                    .where(TelegramChannel.channel_type.in_(ANALYTICAL_TYPES))
                    .where(TelegramChannel.is_active.is_(True))
                    .order_by(TelegramPost.date.desc())
                    .limit(NEIGHBOR_POST_BUDGET * 2)
                )
                borrowed = [
                    p for p in borrow_result.scalars().all()
                    if str(p.id) not in have_ids
                ]
                borrowed = borrowed[:NEIGHBOR_POST_BUDGET]
                if borrowed:
                    logger.info(
                        f"Story {story_id}: direct pool {len(posts)} posts, "
                        f"borrowed {len(borrowed)} from {len(neighbor_ids)} neighbors"
                    )
                    posts.extend(borrowed)

    # Minimum pool size before pass-0. Kept at 1 (down from 2 on 2026-04-19
    # after dropping aggregators halved the pool on many top stories —
    # hero had only 3 analyst-channel posts, below the old threshold).
    # The analysis will be thinner with one voice, but empty is worse.
    if len(posts) < 1:
        return None

    # Content filter (pass 0, nano): drop posts that are just news rehash
    # or off-topic, so only actual analyst commentary feeds pass-1/pass-2.
    labels = await _pass0_classify_posts(
        posts,
        story_title=story.title_fa or story.title_en or "",
        story_summary=story.summary_fa or story.summary_en or "",
    )
    posts = [p for p, lb in zip(posts, labels) if lb == "analysis"]

    if len(posts) < 1:
        logger.info(f"Telegram analysis skipped for {story_id}: 0 analytical posts after pass-0 filter")
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
    # Skip Pass 1 when the pool is thin — Pass 2 can read the posts
    # directly, fact extraction adds no signal on <5 posts and burns a
    # nano call per qualifying story.
    if len(posts) < 5:
        facts_data = None
        facts_json = "(استخراج حقایق رد شد — تعداد پست‌های تحلیلی کمتر از ۵)"
        logger.info(f"Telegram story {story_id}: skipping Pass 1 ({len(posts)} posts < 5)")
    else:
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
        # Both tiers now use bias_scoring_model (gpt-4o-mini). The
        # premium tier used to call gpt-5-mini ($2/Mtok output) on the
        # top-5 trending stories, which dominated the monthly bill
        # (~$0.42/day alone) for a quality lift that wasn't visible on
        # the hero card. is_premium is still passed through so the
        # cost dashboard keeps the tier breakdown.
        model = settings.bias_scoring_model
        params = build_openai_params(
            model=model,
            prompt=prompt,
            # 1200 is tight but sufficient: Pass 2 responses (predictions
            # array, key_claims, worldviews, consensus, missing_voices)
            # sit around 1100-1400 tokens in practice. Was 2000.
            max_tokens=1200,
            temperature=0.2,
        )
        response = await client.chat.completions.create(**params)
        from app.services.llm_usage import log_llm_usage
        tier = "premium" if is_premium else "baseline"
        await log_llm_usage(
            model=model,
            purpose=f"telegram.pass2.{tier}",
            usage=response.usage,
            story_id=story_id,
        )
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

        # Resolve supporter names → real analyst channels so the UI can
        # render "N از T تحلیلگر" instead of the hallucinated pct the
        # LLM used to copy from the prompt example.
        await enrich_predictions_with_analyst_counts(db, result)

        return result

    except Exception as e:
        logger.warning(f"Telegram analysis pass 2 failed for story {story_id}: {e}")
        return None


async def link_posts_by_embedding(db: AsyncSession, threshold: float = 0.35) -> dict:
    """Link unlinked Telegram posts to stories via URL match + embeddings.

    Two-pass:
      1. URL extraction (high precision, ~free): if a post contains a
         URL matching an article URL we already cluster, link directly
         to that article's story. Bypasses embedding entirely — a post
         that explicitly quotes a Reuters link doesn't need fuzzy
         matching.
      2. Embedding similarity fallback: for posts with no article URL,
         score against story centroids AND each article's own embedding,
         taking the MAX. Broad umbrella stories have diluted centroids
         (100+ articles averaged produces a blurry vector); per-article
         rescue finds posts that match one specific article sharply.
    """
    import re
    from urllib.parse import urlparse

    from app.models.article import Article
    from app.nlp.embeddings import generate_embeddings_batch, cosine_similarity
    from sqlalchemy import update

    # ── Pass 1: URL extraction ──
    # Build an index of article_url → story_id so we can lookup in O(1).
    # Only include articles in stories we'd consider anyway (≥3 articles,
    # matching the centroid query below). ~3K articles, cheap.
    art_index_result = await db.execute(
        select(Article.url, Article.story_id)
        .where(Article.story_id.isnot(None), Article.url.isnot(None))
    )
    url_to_story: dict[str, str] = {}
    for art_url, sid in art_index_result.all():
        if art_url and sid:
            url_to_story[art_url] = str(sid)
            # Also index by (host, path) so paywall redirects and query
            # strings don't block matches on the same article
            try:
                u = urlparse(art_url)
                key = f"{u.hostname}{u.path}".lower().rstrip("/")
                url_to_story.setdefault(key, str(sid))
            except Exception:
                pass

    # Match http(s) URLs only; ignore tg:// and bare mentions.
    URL_RE = re.compile(r"https?://[^\s<>\"\)]+", re.I)

    def _find_story_via_url(text: str) -> str | None:
        """Return the story_id of the first article URL cited in `text`,
        or None. Matches on exact URL first, then on (host, path) for
        resilience to utm params / fragment differences."""
        if not text:
            return None
        for raw in URL_RE.findall(text):
            # Strip trailing punctuation Telegram captures sometimes glue on
            clean = raw.rstrip(".,;:!؟،؛")
            if clean in url_to_story:
                return url_to_story[clean]
            try:
                u = urlparse(clean)
                key = f"{u.hostname}{u.path}".lower().rstrip("/")
                if key in url_to_story:
                    return url_to_story[key]
            except Exception:
                continue
        return None

    # ── Pass 2 prep: centroids + per-article embeddings ──
    result = await db.execute(
        select(Story).where(
            Story.centroid_embedding.isnot(None),
            Story.article_count >= 3,
        )
    )
    stories = list(result.scalars().all())

    # Validate centroids — some rows have dicts, lists with None values, or
    # partially-initialized vectors from older code. Skip anything that
    # isn't a clean list of finite numbers so cosine_similarity can't raise.
    def _clean_vec(v) -> list[float] | None:
        if not isinstance(v, list) or len(v) == 0:
            return None
        if any(x is None or not isinstance(x, (int, float)) for x in v):
            return None
        return v

    story_centroids: dict[str, list[float]] = {}
    for s in stories:
        c = _clean_vec(s.centroid_embedding)
        if c is not None:
            story_centroids[str(s.id)] = c

    if not story_centroids:
        return {"linked": 0, "reason": "no stories with centroids"}

    # Pull article embeddings for every story we're considering.
    # 200 stories × ~6 articles average = ~1200 vectors, cheap.
    eligible_ids = list(story_centroids.keys())
    article_result = await db.execute(
        select(Article.story_id, Article.embedding)
        .where(
            Article.story_id.in_(eligible_ids),
            Article.embedding.isnot(None),
        )
    )
    story_article_embs: dict[str, list[list[float]]] = {}
    for sid, emb in article_result.all():
        cleaned = _clean_vec(emb)
        if cleaned is None:
            continue
        story_article_embs.setdefault(str(sid), []).append(cleaned)

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

    # ── Pass 1: URL extraction (high-precision, zero LLM) ──
    linked_by_url = 0
    remaining_posts = []
    for post in posts:
        sid = _find_story_via_url(post.text or "")
        if sid:
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.id == post.id)
                .values(story_id=sid)
            )
            linked_by_url += 1
        else:
            remaining_posts.append(post)

    # ── Pass 2: Embedding similarity on whatever URL didn't catch ──
    if not remaining_posts:
        await db.commit()
        logger.info(f"URL-linked {linked_by_url} posts, no residual for embedding pass")
        return {
            "linked": linked_by_url,
            "total_posts": len(posts),
            "via_url": linked_by_url,
            "via_embedding": 0,
            "threshold": threshold,
        }

    post_texts = [(p.text or "")[:500] for p in remaining_posts]
    embeddings = generate_embeddings_batch(post_texts, batch_size=100)

    linked_by_embedding = 0
    via_article_rescue = 0
    for post, emb in zip(remaining_posts, embeddings):
        if not emb or all(v == 0 for v in emb) or any(v is None for v in emb):
            continue

        best_score = 0.0
        best_story_id: str | None = None
        best_via_article = False

        for sid, centroid in story_centroids.items():
            try:
                centroid_score = cosine_similarity(emb, centroid)
            except Exception:
                centroid_score = 0.0

            # Per-article best match for this story (rescues broad clusters
            # whose centroid is blurred by too many heterogeneous articles).
            article_best = 0.0
            for art_emb in story_article_embs.get(sid, []):
                try:
                    s = cosine_similarity(emb, art_emb)
                except Exception:
                    continue
                if s > article_best:
                    article_best = s

            used_article = article_best > centroid_score
            score = max(centroid_score, article_best)

            if score > best_score:
                best_score = score
                best_story_id = sid
                best_via_article = used_article

        if best_score >= threshold and best_story_id:
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.id == post.id)
                .values(story_id=best_story_id)
            )
            linked_by_embedding += 1
            if best_via_article:
                via_article_rescue += 1

    await db.commit()
    total_linked = linked_by_url + linked_by_embedding
    logger.info(
        f"Linked {total_linked} telegram posts "
        f"(url={linked_by_url}, embedding={linked_by_embedding}, "
        f"via_article_rescue={via_article_rescue}, threshold={threshold})"
    )
    return {
        "linked": total_linked,
        "total_posts": len(posts),
        "via_url": linked_by_url,
        "via_embedding": linked_by_embedding,
        "via_article_rescue": via_article_rescue,
        "threshold": threshold,
    }


async def reassign_posts_by_embedding(
    db: AsyncSession,
    *,
    sample_limit: int = 3000,
    drift_gap: float = 0.08,
    min_score: float = 0.40,
) -> dict:
    """Re-examine already-linked Telegram posts and move any whose best
    current-story match is no longer their best match overall.

    Why: link_posts_by_embedding only runs on posts with story_id=NULL,
    so a post's initial attachment is permanent even when its original
    story fragments, merges with another, or ages out while a better
    cluster forms nearby. Over weeks that produces stale mis-links —
    posts show up as "commentary" on a story they stopped matching.

    Rules:
      - Only consider posts whose alternative story scores `drift_gap`
        HIGHER than their current story (default 0.08). Prevents
        thrashing around borderline matches.
      - Require the alternative to clear `min_score` (default 0.40) —
        slightly stricter than the link threshold 0.35, because
        reassignment is a stronger claim than initial attachment.
      - Cap at `sample_limit` posts per run to stay within step
        timeout; orders by most recently posted first so freshest
        discourse corrects first.

    Returns per-run stats including the story IDs whose post count
    shifted — caller can invalidate their telegram_analysis cache so
    the next read regenerates.
    """
    from sqlalchemy import desc, update

    from app.models.article import Article
    from app.nlp.embeddings import cosine_similarity

    def _clean_vec(v) -> list[float] | None:
        if not isinstance(v, list) or len(v) == 0:
            return None
        if any(x is None or not isinstance(x, (int, float)) for x in v):
            return None
        return v

    # Load stories with valid centroids (same guard as the linker)
    result = await db.execute(
        select(Story).where(
            Story.centroid_embedding.isnot(None),
            Story.article_count >= 3,
        )
    )
    stories = list(result.scalars().all())
    story_data: dict[str, list[float]] = {}
    for s in stories:
        c = _clean_vec(s.centroid_embedding)
        if c is not None:
            story_data[str(s.id)] = c

    if not story_data:
        return {"reassigned": 0, "reason": "no stories with centroids"}

    # Per-article embeddings give reassignment the same rescue path as
    # initial linking: a post that matches one specific article in a
    # broad cluster stays (or moves) where that article lives, not
    # where a diluted centroid accidentally wins.
    art_result = await db.execute(
        select(Article.story_id, Article.embedding)
        .where(
            Article.story_id.in_(list(story_data.keys())),
            Article.embedding.isnot(None),
        )
    )
    story_article_embs: dict[str, list[list[float]]] = {}
    for sid, emb in art_result.all():
        cleaned = _clean_vec(emb)
        if cleaned is None:
            continue
        story_article_embs.setdefault(str(sid), []).append(cleaned)

    # Pull a recent sample of linked posts. Posts older than ~60 days
    # rarely benefit from reassignment (their topic has moved on) and
    # walking the full table takes minutes, so window by recency.
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)

    result = await db.execute(
        select(TelegramPost)
        .where(
            TelegramPost.story_id.isnot(None),
            TelegramPost.text.isnot(None),
            TelegramPost.text != "",
            TelegramPost.date >= cutoff,
        )
        .order_by(desc(TelegramPost.date))
        .limit(sample_limit)
    )
    posts = list(result.scalars().all())
    if not posts:
        return {"reassigned": 0, "examined": 0}

    # Re-embed post texts. Using the same batched embedder the linker
    # uses so the vector space matches story centroids exactly.
    from app.nlp.embeddings import generate_embeddings_batch
    post_texts = [(p.text or "")[:500] for p in posts]
    embeddings = generate_embeddings_batch(post_texts, batch_size=100)

    moves: dict[str, int] = {}  # story_id -> net delta
    reassigned = 0
    below_gap = 0
    unchanged = 0

    for post, emb in zip(posts, embeddings):
        if not emb or all(v == 0 for v in emb) or any(v is None for v in emb):
            continue

        current_story = str(post.story_id)
        current_score = 0.0
        best_story_id = current_story
        best_score = 0.0

        for sid, centroid in story_data.items():
            try:
                centroid_score = cosine_similarity(emb, centroid)
            except Exception:
                centroid_score = 0.0
            article_best = 0.0
            for art_emb in story_article_embs.get(sid, []):
                try:
                    s = cosine_similarity(emb, art_emb)
                except Exception:
                    continue
                if s > article_best:
                    article_best = s
            score = max(centroid_score, article_best)

            if sid == current_story:
                current_score = score
            if score > best_score:
                best_score = score
                best_story_id = sid

        if best_story_id == current_story:
            unchanged += 1
            continue

        if best_score < min_score:
            below_gap += 1
            continue

        if (best_score - current_score) < drift_gap:
            below_gap += 1
            continue

        await db.execute(
            update(TelegramPost)
            .where(TelegramPost.id == post.id)
            .values(story_id=best_story_id)
        )
        reassigned += 1
        moves[current_story] = moves.get(current_story, 0) - 1
        moves[best_story_id] = moves.get(best_story_id, 0) + 1

    # Invalidate cached telegram_analysis on every story whose post
    # count changed — the next API read will regenerate with the
    # corrected post set instead of returning stale predictions.
    affected_story_ids = {sid for sid, delta in moves.items() if delta != 0}
    if affected_story_ids:
        await db.execute(
            update(Story)
            .where(Story.id.in_(affected_story_ids))
            .values(telegram_analysis=None)
        )

    await db.commit()
    logger.info(
        f"Reassigned {reassigned} telegram posts across {len(affected_story_ids)} "
        f"stories (examined={len(posts)}, unchanged={unchanged}, below_gap={below_gap}, "
        f"drift_gap={drift_gap}, min_score={min_score})"
    )
    return {
        "reassigned": reassigned,
        "examined": len(posts),
        "unchanged": unchanged,
        "below_gap": below_gap,
        "stories_touched": len(affected_story_ids),
        "drift_gap": drift_gap,
        "min_score": min_score,
    }

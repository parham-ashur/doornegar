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
You are a senior media bias analyst specializing in Iranian news media. You understand \
the Islamic Republic's media ecosystem, the divide between state-controlled outlets inside \
Iran (فارس، تسنیم، ایرنا، کیهان), semi-state outlets with factional leanings (شرق، اعتماد، \
ایران)، independent domestic outlets, and diaspora/opposition outlets abroad (ایران‌اینترنشنال، \
بی‌بی‌سی‌فارسی، صدای‌آمریکا، رادیو فردا، کیهان لندن، ایندیپندنت‌فارسی).

Your job: given an article's text only (source is HIDDEN — never guess it), produce \
structured bias ratings the Doornegar platform uses to show Iranian readers how different \
outlets frame the same events. You must be consistent — the same article analyzed twice \
should get near-identical scores.

# CONTEXT: Iranian media framing patterns

State-aligned outlets typically:
- Call protests فتنه (sedition), اغتشاش (riot), بلوا (unrest); call protesters اغتشاشگر / آشوبگر / عوامل بیگانه (rioters / agents of foreign powers)
- Frame sanctions as "جنگ اقتصادی" (economic war), "ظالمانه", "یکجانبه‌گرایی آمریکا"
- Refer to opposition as ضدانقلاب (counter-revolutionary), معاند (adversary), منافق (hypocrite = MEK)
- Quote or celebrate مقام معظم رهبری (Supreme Leader) and سپاه (IRGC) favorably
- Use شهادت (martyrdom), مقاومت (resistance), دشمن (enemy), سلطه‌گر (hegemon)
- Downplay domestic economic problems; emphasize US/Israel malice

Diaspora/opposition outlets typically:
- Call the same protests قیام (uprising), انقلاب ژینا (Jina/Mahsa revolution), خیزش سراسری
- Frame sanctions as leverage or justified, or at least as America's right
- Refer to security forces as سرکوبگر (repressor), نیروهای سرکوب, گزمه
- Highlight prisoners, executions, economic collapse, women's rights, minority rights
- Use کشتار (massacre), اعدام (execution), زندانی سیاسی (political prisoner), کودک‌کشی (child-killing)
- Often cite ICHR, Amnesty, CHRI, Iran Human Rights, HRANA

Independent domestic outlets try to:
- Use neutral terms: معترضان (protesters), اعتراضات (protests), درگیری (clashes)
- Cite multiple viewpoints, present economic data with context
- Avoid pejoratives from both sides
- Report on reformist and conservative factions without loaded language

Loaded Persian terms to recognize (state → opposition equivalents):
- شهید (martyr) ↔ قربانی (victim) — state calls dead security forces martyrs
- مقاومت (resistance) ↔ درگیری / حمله (clash / attack)
- دشمن (enemy) ↔ طرف مقابل (opposing party)
- فتنه (sedition) ↔ اعتراض (protest)
- اراذل و اوباش (thugs) ↔ معترضان (protesters)
- عوامل بیگانه (foreign agents) ↔ شهروندان ناراضی (dissatisfied citizens)
- نظام / جمهوری اسلامی ↔ حکومت ایران / رژیم (regime)

# SCORING RUBRIC

## political_alignment (-1.0 to +1.0)
- -1.0: strongly pro-establishment, celebratory of Supreme Leader/IRGC, uses state framing
- -0.5: sympathetic to establishment, uses some state terms but not fully propagandistic
-  0.0: neutral, fact-based, no clear alignment
- +0.5: critical of establishment, uses opposition framing but still reports facts
- +1.0: strongly anti-establishment, uses full opposition framing, celebrates protests/exiles

## pro_regime_score, reformist_score, opposition_score (each 0.0-1.0)
How strongly does the article align with that specific camp? These are not mutually \
exclusive — a reformist piece can have reformist_score=0.7 and opposition_score=0.3.

## tone_score (-1.0 to +1.0)
- -1.0: alarming, doom-laden, crisis framing
-  0.0: neutral, informational
- +1.0: celebratory, triumphalist

## emotional_language_score (0.0-1.0)
- 0.0: dry facts, wire-service prose
- 0.5: some adjectives, mild framing
- 1.0: propaganda-grade — loaded words in nearly every sentence

## factuality_score (0.0-1.0)
- 0.0: pure opinion, no sources, makes claims without evidence
- 0.5: some facts mixed with speculation; single-sourced
- 1.0: multiple named sources, specific data, allows counter-viewpoints

## source_citation_count / anonymous_source_count
Count literal citations: "according to X", "officials said", "reports indicate". \
Named = X is identified. Anonymous = unnamed source / "officials" / "reports".

## uses_loaded_language (bool)
True if the article uses any of the loaded terms above, or their equivalents.

## framing_labels
Pick 1-3 from: {framing_labels}

# FEW-SHOT EXAMPLES

## Example A (clearly state-aligned)

Title: دستگیری عوامل فتنه اخیر / عناصر وابسته به سرویس‌های بیگانه
Text: به گزارش خبرنگار ما، نیروهای امنیتی موفق شدند تعدادی از اغتشاشگران و عوامل وابسته به سرویس‌های \
بیگانه که قصد ایجاد ناامنی در کشور را داشتند، دستگیر کنند. یک مقام آگاه اعلام کرد این افراد با \
هدایت رسانه‌های معاند قصد برهم زدن نظم عمومی را داشتند. مقام معظم رهبری پیش‌تر درباره توطئه دشمنان \
هشدار داده بودند.

Expected output (for calibration — you will analyze a different article):
{{
  "political_alignment": -0.85,
  "pro_regime_score": 0.9,
  "reformist_score": 0.0,
  "opposition_score": 0.0,
  "framing_labels": ["security", "western_interference", "sovereignty"],
  "tone_score": -0.3,
  "emotional_language_score": 0.8,
  "factuality_score": 0.2,
  "source_citation_count": 0,
  "anonymous_source_count": 1,
  "uses_loaded_language": true,
  "reasoning_en": "Uses fully state framing (اغتشاشگران/عوامل وابسته/معاند/توطئه), cites only an anonymous official, and centers the Supreme Leader as authoritative.",
  "reasoning_fa": "از ادبیات کاملاً حکومتی استفاده شده و فقط به یک منبع ناشناس و سخن رهبری استناد کرده، بدون دیدگاه مقابل."
}}

## Example B (clearly diaspora/opposition)

Title: سرکوب معترضان در کردستان / گزارش‌هایی از کشته‌شدن چند شهروند
Text: بر اساس گزارش‌های دریافتی از فعالان حقوق بشر و تصاویر منتشرشده در شبکه‌های اجتماعی، نیروهای \
سرکوب جمهوری اسلامی در چند شهر کردستان به سوی معترضان تیراندازی کرده‌اند. سازمان حقوق بشر ایران \
اعلام کرد دست‌کم چهار شهروند کشته و ده‌ها نفر بازداشت شده‌اند. یکی از شاهدان گفت: «نیروها بدون \
هشدار به سمت جمعیت شلیک کردند.»

Expected output:
{{
  "political_alignment": 0.85,
  "pro_regime_score": 0.0,
  "reformist_score": 0.05,
  "opposition_score": 0.9,
  "framing_labels": ["human_rights", "victimization", "conflict"],
  "tone_score": -0.7,
  "emotional_language_score": 0.6,
  "factuality_score": 0.6,
  "source_citation_count": 1,
  "anonymous_source_count": 1,
  "uses_loaded_language": true,
  "reasoning_en": "Uses full opposition framing (نیروهای سرکوب/جمهوری اسلامی), cites a named NGO (Iran HR), centers victim and witness perspective, and uses دست‌کم N کشته (at least N killed) — a typical diaspora-media pattern.",
  "reasoning_fa": "از چارچوب‌بندی اپوزیسیون استفاده شده؛ به یک نهاد حقوق بشری و یک شاهد ناشناس استناد می‌کند و لحن به‌شدت انتقادی است."
}}

## Example C (neutral / independent)

Title: نرخ تورم ماهانه به ۳٫۲ درصد رسید / اعلام مرکز آمار
Text: مرکز آمار ایران اعلام کرد نرخ تورم نقطه‌به‌نقطه در ماه گذشته به ۳۲ درصد رسیده است. احمد رضایی، \
اقتصاددان دانشگاه تهران، در گفتگو با ما گفت این رقم از سقف پیش‌بینی‌های اولیه بالاتر است اما روند \
کند شدنی را نشان می‌دهد. گزارش کامل مرکز آمار در وبگاه این نهاد منتشر شده است.

Expected output:
{{
  "political_alignment": 0.05,
  "pro_regime_score": 0.1,
  "reformist_score": 0.1,
  "opposition_score": 0.1,
  "framing_labels": ["economic_impact"],
  "tone_score": -0.1,
  "emotional_language_score": 0.1,
  "factuality_score": 0.9,
  "source_citation_count": 2,
  "anonymous_source_count": 0,
  "uses_loaded_language": false,
  "reasoning_en": "Straightforward economic reporting with two named sources (official statistics + a named academic) and no loaded language. Slight negative tone is the subject matter (rising inflation), not framing.",
  "reasoning_fa": "گزارش اقتصادی مستقیم با دو منبع نامبرده و بدون ادبیات بارگذاری‌شده. لحن کمی منفی به‌دلیل خود موضوع (افزایش تورم) است، نه چارچوب‌بندی."
}}

# OUTPUT FORMAT

You MUST return a single JSON object only — no prose, no markdown code fences, no \
commentary. Use this exact schema:

{{
  "political_alignment": <float -1.0 to 1.0>,
  "pro_regime_score": <float 0.0 to 1.0>,
  "reformist_score": <float 0.0 to 1.0>,
  "opposition_score": <float 0.0 to 1.0>,
  "framing_labels": <list of 1-3 strings from: {framing_labels}>,
  "tone_score": <float -1.0 to 1.0>,
  "emotional_language_score": <float 0.0 to 1.0>,
  "factuality_score": <float 0.0 to 1.0>,
  "source_citation_count": <int>,
  "anonymous_source_count": <int>,
  "uses_loaded_language": <bool>,
  "reasoning_en": "<2-3 sentences in English>",
  "reasoning_fa": "<2-3 sentences in Persian>"
}}

# ARTICLE TO ANALYZE

Title: {title}

Text: {text}
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


async def _keepalive(db: AsyncSession) -> None:
    """Ping the DB connection with SELECT 1 to reset Neon's idle timer.

    Neon closes idle connections after ~5 min. Bias scoring loops through
    articles with a ~5-10s LLM call per article — if the loop is long
    enough, the session's underlying connection dies. Calling this before
    each LLM call keeps the gap between DB touches far under 5 min.
    """
    from sqlalchemy import text
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Bias scoring keepalive ping failed: {e}")


async def score_unscored_articles(
    db: AsyncSession, batch_size: int = 20, visible_stories_only: bool = False,
) -> dict:
    """Score articles that don't have bias scores yet.

    Cost optimization: when visible_stories_only=True, only scores articles
    in stories with article_count >= 5 (visible on homepage). This avoids
    spending LLM tokens on articles in tiny clusters nobody sees.

    Returns stats: {scored, failed, skipped}.
    """
    from datetime import timedelta as _td
    from app.models.story import Story

    scored_article_ids = select(BiasScore.article_id).distinct()
    now = datetime.now(timezone.utc)
    retry_cutoff = now - _td(hours=24)

    query = select(Article).where(
        Article.id.notin_(scored_article_ids),
        Article.story_id.isnot(None),
        (Article.llm_failed_at.is_(None)) | (Article.llm_failed_at < retry_cutoff),
    )

    # Only score articles in visible stories (saves ~60% of bias scoring cost)
    if visible_stories_only:
        visible_story_ids = select(Story.id).where(Story.article_count >= 5)
        query = query.where(Article.story_id.in_(visible_story_ids))

    result = await db.execute(query.limit(batch_size))
    articles = result.scalars().all()

    stats = {"scored": 0, "failed": 0, "skipped": 0}

    for article in articles:
        if not article.content_text and not article.summary:
            stats["skipped"] += 1
            continue

        await _keepalive(db)
        bias_score = await score_article_bias(article, db)
        if bias_score:
            stats["scored"] += 1
            article.llm_failed_at = None  # clear any previous failure flag
        else:
            stats["failed"] += 1
            article.llm_failed_at = now  # mark so we don't retry for 24h
        await db.commit()  # commit per article — partial progress survives

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
    """Call Anthropic Claude API (fallback only — primary path is OpenAI)."""
    import anthropic

    # bias_scoring_model may be an OpenAI model name; fall back to a
    # reasonable Claude default if so.
    model = settings.bias_scoring_model
    if not model.startswith("claude-"):
        model = "claude-haiku-4-5-20251001"

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _call_openai(prompt: str) -> str:
    """Call OpenAI API."""
    import openai

    from app.services.llm_helper import build_openai_params

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.bias_scoring_model,
        prompt=prompt,
        max_tokens=1024,
        temperature=0.3,
    )
    response = await client.chat.completions.create(**params)
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

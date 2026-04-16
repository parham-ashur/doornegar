"""Story summarization and bias explanation using OpenAI.

Generates rich Farsi analysis for stories including:
- Overall summary based on full article content
- Per-side summaries (state vs diaspora vs independent)
- Structured bias scores (tone, framing, factuality per side)
"""

import json
import logging

import openai

from app.config import settings

logger = logging.getLogger(__name__)

ALIGNMENT_LABELS_FA = {
    "state": "حکومتی",
    "semi_state": "نیمه‌حکومتی",
    "independent": "مستقل",
    "diaspora": "برون‌مرزی",
}

STORY_ANALYSIS_PROMPT = """\
شما یک تحلیلگر ارشد رسانه‌ای هستید که برای پلتفرم شفافیت رسانه‌ای «دورنگر» کار می‌کنید. \
هدف: نشان دادن تفاوت‌های چارچوب‌بندی بین رسانه‌های حکومتی و اپوزیسیون — تا خواننده خودش قضاوت کند.

# سبک نوشتار

- فارسی معیار و رسمی، نه محاوره‌ای.
- راوی بی‌طرف — از ادبیات هیچ طرفی استفاده نکنید.
- واژگان بارگذاری‌شده را فقط با گیومه «» نقل کنید.
- به شواهد عینی توجه کنید: ارقام، آمار، نام افراد، تاریخ‌ها، اسناد. این جزئیات را در عنوان و تحلیل بگنجانید.

# واژگان رسانه‌ای ایرانی

حکومتی: فتنه، اغتشاش، شهید، مقاومت، دشمن، عوامل بیگانه، ضدانقلاب، تحریم ظالمانه
اپوزیسیون: قیام، سرکوب، کشتار، زندانی سیاسی، حقوق بشر، رژیم ایران، جان‌باخته
مستقل: معترضان، کشته‌شدگان، نیروهای امنیتی (واژگان خنثی)

# مقالات

{articles_block}

# عنوان (تیتر صفحه اصلی — مهم‌ترین خروجی)

عنوان = خلاصه رویداد. خواننده باید فقط با خواندن عنوان بفهمد چه اتفاقی افتاده.
- حداکثر ۱۵ کلمه. جزئیات کلیدی: ارقام، نام‌ها، شرایط، نتیجه.
- اگر عدد یا آمار مهمی وجود دارد (تعداد کشته، مبلغ، مدت زمان) حتماً در عنوان بیاورید.
- مثال خوب: «آتش‌بس دو هفته‌ای ایران و آمریکا؛ طرح ۱۰ ماده‌ای با میانجیگری پاکستان»
- مثال خوب: «شکست مذاکرات اسلام‌آباد؛ ونس بدون توافق بازگشت، ایران زمان‌بندی ندارد»
- مثال بد: «توافق آتش‌بس بین ایران و آمریکا و واکنش‌های جهانی» (کلی، بدون جزئیات)

# تحلیل سوگیری (مهم‌ترین بخش بعد از عنوان)

bias_explanation_fa باید عمیق و مشخص باشد. ۵ تا ۷ نکته مجزا، هر کدام یک جمله. با نقطه‌ویرگول (؛) جدا کن.

هر نکته باید یکی از این الگوها را دنبال کند:
۱. چه چیزی حکومتی پنهان کرد / نادیده گرفت که اپوزیسیون پوشش داد (یا بالعکس)
۲. واژه‌ای بارگذاری‌شده که یک طرف استفاده کرد — با نقل مستقیم «»
۳. تفاوت لحن: پیروزمندانه vs هشداردهنده، سوگوار vs تهاجمی
۴. حقیقتی که یک طرف تحریف کرد یا بزرگ‌نمایی کرد — با ذکر ارقام و شواهد مشخص
۵. منبعی که یک طرف نقل کرد اما طرف دیگر نادیده گرفت
۶. تفاوت در ارائه آمار و ارقام — فقط وقتی هر دو طرف دربارهٔ **یک موضوع واحد** آمار داده‌اند (مثلاً هر دو دربارهٔ «تعداد تلفات حملات ۱۳ آوریل» حرف می‌زنند اما ارقام متفاوت می‌دهند). موضوع مشترک را صراحتاً نام ببر. اگر یکی از «مدت آتش‌بس» و دیگری از «مدت جنگ» صحبت می‌کند، مقایسه نکن — اینها دو موضوع متفاوتند حتی اگر هر دو عدد روز باشند

# امتیاز اختلاف (dispute_score) — برای بخش «بیشترین اختلاف نظر» در صفحه اصلی
# 0.0 = هر دو طرف بر سر حقایق توافق دارند (فقط تفاوت لحن)
# 0.5 = اختلاف قابل‌توجه در چارچوب‌بندی و واقعیت‌های گزارش‌شده
# 1.0 = تناقض کامل — ادعاهای کاملاً متضاد، واقعیت‌های متفاوت

# واژگان بارگذاری‌شده (loaded_words) — برای بخش «واژه‌های هفته» در صفحه اصلی
# ۳ واژه یا عبارت بارگذاری‌شده‌ای که هر طرف در مقالاتش استفاده کرده
# مثلاً: conservative: ["پیروزی بزرگ", "محور مقاومت", "تسلیم دشمن"]
# مثلاً: opposition: ["آتش‌بس شکننده", "قطع اینترنت", "بحران انسانی"]

# امتیاز بی‌طرفی رسانه‌ها (برای نمودار جایگاه رسانه‌ها)

برای هر رسانه‌ای که در این مجموعه مقالات حضور دارد، یک امتیاز بی‌طرفی بدهید:
- مقیاس: -1.0 (کاملاً یک‌طرفه و جانبدارانه) تا +1.0 (کاملاً بی‌طرف و متوازن)
- -1.0: فقط یک روایت، بدون نقل دیدگاه مقابل، واژگان بارگذاری‌شده
- 0.0: نسبتاً متعادل ولی با تمایل مشخص
- +1.0: پوشش متوازن، نقل هر دو طرف، واژگان خنثی
- فرمت: slug رسانه → عدد. مثلاً: {{"bbc-persian": 0.3, "fars-news": -0.8}}

# خروجی

فقط JSON. بدون توضیح اضافی، بدون بلوک کد markdown.

{{
  "title_fa": "<تیتر خبری ۸-۱۲ کلمه — فقط جوهره رویداد: چه اتفاقی افتاد، کجا، چه ارقامی. هرگز از این واژه‌ها استفاده نکن: تحلیل، سوگیری، پوشش رسانه‌ای، روایت، بررسی، مقایسه، نقش عوامل خارجی. تیتر باید مثل روزنامه باشد نه عنوان پژوهش>",
  "title_en": "<English translation>",
  "summary_fa": "<۱-۲ جمله، ۲۰-۳۰ کلمه — فقط حقایق اصلی برای کارت صفحه اصلی>",
  "state_summary_fa": "<روایت حکومتی ۳-۴ جمله: چه گفتند، چه واژگانی به‌کار بردند، چه چیزی را پنهان کردند. یا null>",
  "diaspora_summary_fa": "<روایت اپوزیسیون ۳-۴ جمله: چه گفتند، چه واژگانی به‌کار بردند، بر چه تأکید کردند. یا null>",
  "independent_summary_fa": "<روایت مستقل ۲-۳ جمله، یا null>",
  "bias_explanation_fa": "<۵-۷ نکته مجزا با نقطه‌ویرگول (؛) — تحلیل عمیق سوگیری با نقل مستقیم واژگان و ارقام>",
  "scores": {{
    "state": {{"framing": ["حداکثر ۳ از: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"framing": ["حداکثر ۳"]}},
    "independent": {{"framing": ["حداکثر ۳"]}}
  }},
  "source_neutrality": {{
    "<slug رسانه ۱>": <عدد -1.0 تا 1.0>,
    "<slug رسانه ۲>": <عدد -1.0 تا 1.0>
  }},
  "dispute_score": <عدد 0.0 تا 1.0 — میزان تناقض بین روایت‌ها. 0=توافق، 0.5=اختلاف قابل‌توجه، 1=تناقض کامل>,
  "loaded_words": {{
    "conservative": ["<واژه بارگذاری‌شده ۱ محافظه‌کار>", "<واژه ۲>", "<واژه ۳>"],
    "opposition": ["<واژه بارگذاری‌شده ۱ اپوزیسیون>", "<واژه ۲>", "<واژه ۳>"]
  }},
  "narrative_arc": {{
    "evolution": "<اگر موضوعات مرتبط اخیر ارائه شده: چگونه روایت از آن زمان تا حالا تغییر کرده، ۱-۲ جمله. اگر ارائه نشده: null>",
    "vocabulary_shift": ["<واژه‌ای که در پوشش قبلی بود ولی در جدید نیست>", "<واژه جدیدی که جایگزین شده>"],
    "direction": "<escalating | de-escalating | shifting | stable>"
  }},
  "delta": "<اگر خلاصه قبلی ارائه شده: فقط اطلاعات جدید نسبت به تحلیل قبلی، ۱-۲ جمله. تکرار نکن. اگر ارائه نشده: null>"
}}"""


# ── Deep analyst factors (premium tier only) ──────────────────────
# Appended to the prompt for top-N trending stories to generate
# structured analytical factors alongside the summary/bias comparison.
# This is the "Doornegar AI Analyst" — tagged so future human analysts
# from Telegram can sit alongside it.

ANALYST_FACTORS_ADDENDUM = """

# تحلیل عمیق (فقط برای موضوعات مهم)

علاوه بر خلاصه بالا، یک تحلیل عمیق به‌عنوان «تحلیلگر هوش مصنوعی دورنگر» ارائه بده.
برای هر مورد زیر که مرتبط است، یک پاسخ فارسی مختصر (۱-۳ جمله) بنویس.
اگر موردی به این رویداد مرتبط نیست، null بگذار.

فیلد "analyst" را به JSON خروجی اضافه کن:

"analyst": {{
  "id": "doornegar-ai",
  "name_fa": "تحلیلگر هوش مصنوعی دورنگر",
  "type": "llm",

  "risk_assessment": "<چه خطراتی وجود دارد؟ برای چه کسانی؟ یا null>",
  "potential_outcomes": ["<سناریو محتمل ۱>", "<سناریو ۲>", "<سناریو ۳>"],
  "key_stakeholders": ["<بازیگر ۱: نقش/منافع>", "<بازیگر ۲: نقش/منافع>"],
  "missing_information": "<چه اطلاعاتی هنوز نداریم؟ چه سؤالاتی بی‌پاسخ مانده؟ یا null>",
  "credibility_signals": "<کدام ادعاها تأیید شده، کدام تأیید نشده، کدام احتمالاً تبلیغاتی هستند؟ یا null>",
  "timeline": {{"short_term": "<روزها>", "medium_term": "<هفته‌ها>", "long_term": "<ماه‌ها>"}},
  "framing_gap": "<بزرگ‌ترین تفاوت بین روایت حکومتی و برون‌مرزی در یک جمله>",
  "what_is_hidden": {{"state_omits": "<حکومتی چه چیزی را نمی‌گوید؟>", "diaspora_omits": "<برون‌مرزی چه چیزی را نمی‌گوید؟>"}},
  "historical_parallel": "<آیا رویداد مشابهی در گذشته رخ داده؟ نتیجه‌اش چه بود؟ یا null>",
  "economic_impact": "<تأثیر بر اقتصاد، تحریم‌ها، نرخ ارز، نفت؟ یا null>",
  "international_implications": "<واکنش بین‌المللی، سازمان ملل، اتحادیه اروپا؟ یا null>",
  "factional_dynamics": "<کدام جناح سیاسی (اصولگرا، اصلاح‌طلب، سپاه) از این بهره می‌برد؟ یا null>",
  "human_rights_dimension": "<آیا حقوق بشر، آزادی بیان، حقوق زنان، اقلیت‌ها مطرح است؟ یا null>",
  "public_sentiment": "<واکنش مردم در شبکه‌های اجتماعی و تلگرام چگونه بوده؟ یا null>",
  "propaganda_watch": "<کدام ادعاهای مشخص از هر طرف نشانه‌های تبلیغاتی دارند؟ یا null>"
}}

قوانین تحلیل:
- بی‌طرف باش. تحلیلگر هیچ طرفی نمی‌گیرد.
- اگر مورد مرتبط نیست، null بگذار. مجبور نیستی همه را پر کنی.
- از واژگان بارگذاری‌شده استفاده نکن — همه را در گیومه «» بگذار.
- potential_outcomes باید حداقل ۲ سناریو داشته باشد.
- key_stakeholders باید نام مشخص ببرد (شخص، سازمان، کشور).
"""


# ── Pass 1 prompt: fact extraction (cheap, nano model) ──────────
FACT_EXTRACTION_PROMPT = """\
از هر مقاله زیر حقایق کلیدی را استخراج کن. فقط JSON برگردان.

{articles_block}

برای هر مقاله برگردان:
{{
  "facts": [
    {{
      "source": "<نام رسانه>",
      "alignment": "<محافظه‌کار یا اپوزیسیون>",
      "claims": ["<ادعای مشخص ۱>", "<ادعای ۲>"],
      "numbers": ["<عدد یا آمار ذکر شده>"],
      "evidence_type": "<رسمی | ناشناس | شاهد عینی | بدون منبع>",
      "key_quote": "<مهم‌ترین نقل‌قول با «»>"
    }}
  ]
}}"""


async def _pass1_extract_facts(
    articles_with_sources: list[dict],
) -> list[dict] | None:
    """Pass 1: Use nano model to extract structured facts from articles.

    Returns a list of fact dicts, or None if extraction fails.
    Cost: ~$0.001 per story (gpt-4.1-nano).
    """
    lines = []
    for i, art in enumerate(articles_with_sources, 1):
        lines.append(f"--- مقاله {i} ---")
        lines.append(f"منبع: {art.get('source_name_fa', '?')} ({art.get('state_alignment', '?')})")
        lines.append(f"عنوان: {art.get('title', '')}")
        # Shorter content for nano — just first 800 chars
        content = (art.get("content", "") or "")[:800]
        if content:
            lines.append(f"متن: {content}")
        lines.append("")

    prompt = FACT_EXTRACTION_PROMPT.format(articles_block="\n".join(lines))

    try:
        from app.services.llm_helper import build_openai_params
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        params = build_openai_params(
            model=settings.translation_model,  # gpt-4.1-nano — cheapest
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
        result = json.loads(text)
        return result.get("facts", []) if isinstance(result, dict) else result
    except Exception as e:
        logger.warning(f"Pass 1 fact extraction failed: {e}")
        return None


async def generate_story_analysis(
    story,
    articles_with_sources: list[dict],
    model: str | None = None,
    include_analyst_factors: bool = False,
    related_stories: list[dict] | None = None,
    source_track_records: dict | None = None,
    old_summary: str | None = None,
) -> dict:
    """Two-pass story analysis for maximum quality.

    Pass 1 (nano, ~$0.001): Extract structured facts from each article
    Pass 2 (premium/baseline): Analyze framing with facts + context

    Context injected into Pass 2 (no extra LLM cost):
    - related_stories: summaries of similar stories for cross-story memory
    - source_track_records: historical reliability per source
    - old_summary: previous summary for delta generation

    Returns:
        dict with all analysis fields
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in .env to use story analysis."
        )

    # ── Pass 1: Fact extraction (cheap) ──
    facts = await _pass1_extract_facts(articles_with_sources)

    # ── Build Pass 2 prompt with enriched context ──
    lines = []
    current_title = story.title_fa or ""
    lines.append(f"عنوان فعلی خبر: {current_title}\n")

    # Inject extracted facts if Pass 1 succeeded
    if facts:
        lines.append("# حقایق استخراج‌شده (از تحلیل اولیه)")
        for i, fact in enumerate(facts, 1):
            src = fact.get("source", "?")
            align = fact.get("alignment", "?")
            claims = fact.get("claims", [])
            numbers = fact.get("numbers", [])
            evidence = fact.get("evidence_type", "?")
            quote = fact.get("key_quote", "")
            lines.append(f"  {i}. {src} ({align}): {'; '.join(claims[:3])}")
            if numbers:
                lines.append(f"     ارقام: {', '.join(numbers[:3])}")
            if evidence != "?":
                lines.append(f"     نوع شواهد: {evidence}")
            if quote:
                lines.append(f"     نقل‌قول: {quote}")
        lines.append("")
        lines.append("از این حقایق برای مقایسه ادعاها و شناسایی تناقض‌ها استفاده کن.\n")

    # Inject cross-story memory
    if related_stories:
        lines.append("# زمینه: موضوعات مرتبط اخیر")
        for rs in related_stories[:3]:
            lines.append(f"  - {rs.get('title', '?')}: {rs.get('summary', '?')[:100]}")
        lines.append("  اگر این خبر ادامه یکی از موضوعات بالاست، به تحول روایت اشاره کن.\n")

    # Inject source track records
    if source_track_records:
        lines.append("# سابقه رسانه‌ها (بر اساس تحلیل‌های قبلی)")
        for slug, record in list(source_track_records.items())[:6]:
            lines.append(f"  - {slug}: {record}")
        lines.append("  از این سابقه برای ارزیابی اعتبار ادعاها استفاده کن.\n")

    # Inject previous summary for delta detection
    if old_summary:
        lines.append("# خلاصه قبلی (تحلیل پیشین این موضوع)")
        lines.append(f"  {old_summary[:300]}")
        lines.append("  فقط اطلاعات جدید را در فیلد delta بنویس. تکرار نکن.\n")

    # Inject telegram media channel posts as supplementary source context
    try:
        from sqlalchemy import select as _sel
        from app.models.social import TelegramChannel as _TC, TelegramPost as _TP
        from app.database import async_session as _as
        async with _as() as _db:
            tg_result = await _db.execute(
                _sel(_TP.text, _TC.title, _TC.political_leaning)
                .join(_TC, _TP.channel_id == _TC.id)
                .where(_TP.story_id == story.id)
                .where(_TP.text.isnot(None))
                .where(_TC.channel_type == "news")
                .order_by(_TP.views.desc().nullslast())
                .limit(10)
            )
            tg_posts = tg_result.all()
            if tg_posts:
                lines.append("# پست‌های تلگرام رسانه‌ها (منابع تکمیلی)")
                for text, ch_title, leaning in tg_posts:
                    lines.append(f"  [{ch_title} ({leaning})]: {(text or '')[:200]}")
                lines.append("  از این پست‌ها برای تکمیل تحلیل منابع و شناسایی واژگان خاص هر طرف استفاده کن.\n")
    except Exception as e:
        logger.warning("Telegram context enrichment failed for story analysis: %s", e)

    # Add raw articles (shorter since facts are already extracted)
    for i, art in enumerate(articles_with_sources, 1):
        alignment_fa = ALIGNMENT_LABELS_FA.get(
            art.get("state_alignment", ""), "نامشخص"
        )
        source_name = art.get("source_name_fa", "نامشخص")
        title = art.get("title", "بدون عنوان")
        content = art.get("content", "")
        published = art.get("published_at") or ""

        lines.append(f"--- مقاله {i} ---")
        lines.append(f"عنوان: {title}")
        lines.append(f"منبع: {source_name} (جهت‌گیری: {alignment_fa})")
        if published:
            lines.append(f"تاریخ انتشار: {published}")
        if content:
            # If we have facts, send less raw content (facts cover the key points)
            cap = len(content) if not facts else min(len(content), 1000)
            lines.append(f"متن: {content[:cap]}")
        lines.append("")

    articles_block = "\n".join(lines)

    prompt = STORY_ANALYSIS_PROMPT.format(articles_block=articles_block)
    if include_analyst_factors:
        prompt += ANALYST_FACTORS_ADDENDUM
    max_tokens = 6144 if include_analyst_factors else 4096

    try:
        from app.services.llm_helper import build_openai_params

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        params = build_openai_params(
            model=model or settings.story_analysis_model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        response = await client.chat.completions.create(**params)
        response_text = response.choices[0].message.content
        return _parse_analysis_response(response_text)

    except openai.APIError as e:
        logger.error(f"OpenAI API error for story {story.id}: {e}")
        raise RuntimeError(f"OpenAI API call failed: {e}")


def _parse_analysis_response(response_text: str) -> dict:
    """Parse JSON response from the LLM."""
    text = response_text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse story analysis response: {e}\nResponse: {response_text[:500]}"
        )
        raise RuntimeError("Failed to parse LLM response as JSON")

    # Ensure required fields
    defaults = {
        "title_fa": None,
        "title_en": None,
        "summary_fa": None,
        "state_summary_fa": None,
        "diaspora_summary_fa": None,
        "independent_summary_fa": None,
        "bias_explanation_fa": None,
        "scores": None,
        "source_neutrality": None,
        "dispute_score": None,
        "loaded_words": None,
        "narrative_arc": None,
        "delta": None,
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result

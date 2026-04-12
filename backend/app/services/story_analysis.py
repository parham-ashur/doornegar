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

# واژگان رسانه‌ای ایرانی

حکومتی: فتنه، اغتشاش، شهید، مقاومت، دشمن، عوامل بیگانه، ضدانقلاب، تحریم ظالمانه
اپوزیسیون: قیام، سرکوب، کشتار، زندانی سیاسی، حقوق بشر، رژیم ایران، جان‌باخته
مستقل: معترضان، کشته‌شدگان، نیروهای امنیتی (واژگان خنثی)

# مقالات

{articles_block}

# عنوان (تیتر صفحه اصلی — مهم‌ترین خروجی)

عنوان = خلاصه رویداد. خواننده باید فقط با خواندن عنوان بفهمد چه اتفاقی افتاده.
- حداکثر ۱۵ کلمه. جزئیات کلیدی: ارقام، نام‌ها، شرایط، نتیجه.
- مثال خوب: «آتش‌بس دو هفته‌ای ایران و آمریکا؛ طرح ۱۰ ماده‌ای با میانجیگری پاکستان»
- مثال خوب: «شکست مذاکرات اسلام‌آباد؛ ونس بدون توافق بازگشت، ایران زمان‌بندی ندارد»
- مثال بد: «توافق آتش‌بس بین ایران و آمریکا و واکنش‌های جهانی» (کلی، بدون جزئیات)

# تحلیل سوگیری (مهم‌ترین بخش بعد از عنوان)

bias_explanation_fa باید عمیق و مشخص باشد. ۵ تا ۷ نکته مجزا، هر کدام یک جمله. با نقطه‌ویرگول (؛) جدا کن.

هر نکته باید یکی از این الگوها را دنبال کند:
۱. چه چیزی حکومتی پنهان کرد / نادیده گرفت که اپوزیسیون پوشش داد (یا بالعکس)
۲. واژه‌ای بارگذاری‌شده که یک طرف استفاده کرد — با نقل مستقیم «»
۳. تفاوت لحن: پیروزمندانه vs هشداردهنده، سوگوار vs تهاجمی
۴. حقیقتی که یک طرف تحریف کرد یا بزرگ‌نمایی کرد
۵. منبعی که یک طرف نقل کرد اما طرف دیگر نادیده گرفت

مثال خوب:
«حکومتی آتش‌بس را «پیروزی بزرگ» خواند و از «تسلیم آمریکا» نوشت؛ اپوزیسیون همان رویداد را «آتش‌بس شکننده» با «آینده نامعلوم» توصیف کرد؛ حکومتی هیچ اشاره‌ای به ۴۰ روز قطع اینترنت نکرد، در حالی که اپوزیسیون آن را محور گزارش قرار داد؛ حکومتی از «محور مقاومت» و «بازدارندگی» سخن گفت، اپوزیسیون از «تبعات انسانی» و «آوارگان»؛ تنها اپوزیسیون به حمله کویت پس از اعلام آتش‌بس اشاره کرد»

# خروجی

فقط JSON. بدون توضیح اضافی، بدون بلوک کد markdown.

{{
  "title_fa": "<تیتر خبری ۱۰-۱۵ کلمه، حاوی جزئیات کلیدی رویداد>",
  "title_en": "<English translation>",
  "summary_fa": "<۱-۲ جمله، ۲۰-۳۰ کلمه — فقط حقایق اصلی برای کارت صفحه اصلی>",
  "state_summary_fa": "<روایت حکومتی ۳-۴ جمله: چه گفتند، چه واژگانی به‌کار بردند، چه چیزی را پنهان کردند. یا null>",
  "diaspora_summary_fa": "<روایت اپوزیسیون ۳-۴ جمله: چه گفتند، چه واژگانی به‌کار بردند، بر چه تأکید کردند. یا null>",
  "independent_summary_fa": "<روایت مستقل ۲-۳ جمله، یا null>",
  "bias_explanation_fa": "<۵-۷ نکته مجزا با نقطه‌ویرگول (؛) — تحلیل عمیق سوگیری با نقل مستقیم واژگان>",
  "scores": {{
    "state": {{"framing": ["حداکثر ۳ از: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"framing": ["حداکثر ۳"]}},
    "independent": {{"framing": ["حداکثر ۳"]}}
  }}
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


async def generate_story_analysis(
    story,
    articles_with_sources: list[dict],
    model: str | None = None,
    include_analyst_factors: bool = False,
) -> dict:
    """Generate rich analysis for a story using article content.

    Args:
        story: The Story ORM object.
        articles_with_sources: List of dicts with keys:
            title, content, source_name_fa, state_alignment
        model: Optional model override (premium vs baseline).
        include_analyst_factors: If True, appends the deep-analyst
            factors addendum to the prompt. Used only for premium-tier
            top-N trending stories. Adds ~1000 output tokens.
        model: Optional explicit model name. If None, uses
            settings.story_analysis_model (the baseline model).
            Callers that want the premium model for top-N trending
            stories should pass settings.story_analysis_premium_model.

    Returns:
        dict with keys: summary_fa, state_summary_fa, diaspora_summary_fa,
        independent_summary_fa, bias_explanation_fa, scores
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in .env to use story analysis."
        )

    # Build articles block with content, source, alignment, AND publish date
    lines = []
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
            lines.append(f"متن: {content}")
        lines.append("")

    # Include current title so LLM can keep it if still accurate
    current_title = story.title_fa or ""
    lines.insert(0, f"عنوان فعلی خبر: {current_title}\n")

    articles_block = "\n".join(lines)

    prompt = STORY_ANALYSIS_PROMPT.format(articles_block=articles_block)
    if include_analyst_factors:
        prompt += ANALYST_FACTORS_ADDENDUM
    # Increase max_tokens when analyst factors are included (~1000 extra output)
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
        "summary_fa": None,
        "state_summary_fa": None,
        "diaspora_summary_fa": None,
        "independent_summary_fa": None,
        "bias_explanation_fa": None,
        "scores": None,
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result

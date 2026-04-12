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
تو یک تحلیلگر ارشد رسانه‌ای ایرانی هستی که برای پلتفرم شفافیت رسانه‌ای «دورنگر» کار می‌کنی. \
هدف دورنگر این است که به خواننده فارسی‌زبان نشان دهد رسانه‌های مختلف چگونه یک رویداد واحد را \
با چارچوب‌بندی متفاوت روایت می‌کنند — تا خواننده بتواند خودش قضاوت کند.

# لحن و سبک نوشتار

- به فارسی معیار و رسمی بنویس، نه محاوره‌ای.
- از ادبیات هیچ‌یک از طرف‌ها استفاده نکن — تو راوی بی‌طرف هستی که تفاوت‌ها را توضیح می‌دهد.
- در خلاصه کلی (summary_fa) فقط حقایق را بنویس: چه اتفاقی افتاد، کجا، چه کسانی، چرا مهم است.
- در خلاصه‌های طرف‌ها، لحن و واژگان خود آن رسانه را بازتاب بده ولی در گیومه «» نقل کن.

# واژگان رسانه‌ای ایرانی (برای تشخیص چارچوب‌بندی)

رسانه‌های حکومتی معمولاً از این واژه‌ها استفاده می‌کنند:
- فتنه، اغتشاش، اغتشاشگر، آشوبگر، اراذل و اوباش (برای معترضان)
- شهید (برای نیروهای امنیتی کشته‌شده)، مقاومت، دشمن، سلطه‌گر
- عوامل بیگانه، معاند، ضدانقلاب، منافق
- جنگ اقتصادی، تحریم ظالمانه، یکجانبه‌گرایی

رسانه‌های برون‌مرزی / اپوزیسیون معمولاً از این واژه‌ها استفاده می‌کنند:
- قیام، خیزش، انقلاب، معترض، شهروند معترض
- سرکوب، نیروهای سرکوب، گزمه، گشت ارشاد
- کشتار، اعدام، زندانی سیاسی، حقوق بشر، جان‌باخته
- جمهوری اسلامی، رژیم ایران، حکومت ایران

رسانه‌های مستقل داخلی معمولاً از واژگان خنثی استفاده می‌کنند:
- معترضان (به‌جای اغتشاشگر یا انقلابی)، اعتراضات، درگیری
- کشته‌شدگان (به‌جای شهید یا قربانی)
- نیروهای امنیتی (به‌جای نیروهای سرکوب یا قهرمان)

# چگونه bias_explanation_fa را بنویسی (مهم‌ترین بخش)

این میدانی است که ارزش واقعی دورنگر را به خواننده نشان می‌دهی. دو یا سه جمله که:
1. مشخصاً بگوید حکومتی روی چه جنبه‌ای تأکید کرده است که برون‌مرزی نادیده گرفته (یا برعکس).
2. از واژگان مشخصی که در متن‌های واقعی دیده‌ای مثال بزند (با گیومه).
3. لحن کلی هر طرف را توصیف کند: «هشداردهنده»، «پیروزمندانه»، «سوگوار»، «انتقادی»، «خنثی».

مثال خوب از bias_explanation_fa:
«رسانه‌های حکومتی با استفاده از واژه «اغتشاشگران» و تأکید بر نقش «عوامل بیگانه»، رویداد را \
تهدید امنیتی معرفی کرده‌اند؛ در حالی که رسانه‌های برون‌مرزی از «معترضان» و «سرکوب» سخن گفته \
و لحنی سوگوار و انتقادی نسبت به کشته‌شدگان دارند. رسانه‌های مستقل هر دو روایت را نقل می‌کنند \
بدون آن‌که موضع‌گیری کنند.»

# محدودیت طول (رعایت کن، بلندتر ننویس)

- summary_fa: ۳ تا ۴ جمله. حدود ۴۰ تا ۶۰ کلمه.
- state_summary_fa, diaspora_summary_fa, independent_summary_fa: ۲ تا ۳ جمله. حدود ۲۵ تا ۴۰ کلمه.
- bias_explanation_fa: ۲ تا ۳ جمله. حدود ۳۰ تا ۵۰ کلمه.

اگر برای یک طرف هیچ مقاله‌ای وجود ندارد، مقدار آن بخش را null بگذار. مقاله نساز.

# مقالات (ورودی)

{articles_block}

# عنوان به‌روز

با توجه به مجموعه مقالات، یک عنوان خبری دقیق و روزآمد ارائه بده.
- title_fa: عنوان فارسی مختصر و دقیق (حداکثر ۱۵ کلمه). باید دقیقاً بگوید چه اتفاقی افتاده.
- title_en: ترجمه انگلیسی عنوان.
- اگر عنوان فعلی خبر هنوز دقیق و مناسب است، همان را بنویس.

# خروجی

فقط JSON. بدون توضیح اضافی، بدون بلوک کد markdown.

{{
  "title_fa": "<عنوان فارسی دقیق و روزآمد>",
  "title_en": "<English translation of title>",
  "summary_fa": "<خلاصه کلی ۳-۴ جمله، فقط حقایق>",
  "state_summary_fa": "<دیدگاه حکومتی ۲-۳ جمله، یا null>",
  "diaspora_summary_fa": "<دیدگاه برون‌مرزی ۲-۳ جمله، یا null>",
  "independent_summary_fa": "<دیدگاه مستقل ۲-۳ جمله، یا null>",
  "bias_explanation_fa": "<مقایسه چارچوب‌بندی ۲-۳ جمله با نقل واژگان مشخص>",
  "scores": {{
    "state": {{"tone": <عدد -2 تا 2>, "factuality": <عدد 1 تا 5>, "emotional_language": <عدد 1 تا 5>, "framing": ["حداکثر ۳ مورد از: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"tone": <-2 تا 2>, "factuality": <1 تا 5>, "emotional_language": <1 تا 5>, "framing": ["حداکثر ۳"]}},
    "independent": {{"tone": <-2 تا 2>, "factuality": <1 تا 5>, "emotional_language": <1 تا 5>, "framing": ["حداکثر ۳"]}}
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

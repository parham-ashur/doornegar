"""Story summarization and bias explanation using OpenAI.

Generates rich Farsi analysis for stories including:
- Overall summary based on full article content
- Structured per-subgroup bullet narratives (principlist / reformist /
  moderate-diaspora / radical-diaspora)
- Legacy flat side summaries (state_summary_fa / diaspora_summary_fa)
  synthesised by joining bullets — kept during the transition window
  so any unmigrated consumer renders something.
- Structured bias scores (framing per side)
"""

import json
import logging

import openai

from app.config import settings
from app.services.narrative_groups import narrative_group as _narrative_group

logger = logging.getLogger(__name__)

# Subgroup labels for prompt presentation. The LLM sees articles tagged
# with these Farsi strings and is asked to cluster its bullet output by
# the same labels.
SUBGROUP_LABELS_FA = {
    "principlist": "اصول‌گرا",
    "reformist": "اصلاح‌طلب",
    "moderate_diaspora": "میانه‌رو",
    "radical_diaspora": "رادیکال",
}


# Loaded-word dictionaries per subgroup — deterministic bias signals.
# Mirror the vocabulary examples in the LLM prompt so the evidence we
# surface in the UI matches the framing rubric. Persian surface forms;
# substring match is fine because these are full words, not roots.
LOADED_WORDS_FA = {
    "principlist": [
        "فتنه", "اغتشاش", "شهید", "شهدا", "مقاومت", "دشمن",
        "عوامل بیگانه", "ضدانقلاب", "تحریم ظالمانه", "محور مقاومت",
        "پیروزی", "استکبار",
    ],
    "reformist": [
        "اصلاحات", "گفت‌وگو", "جامعه مدنی", "حقوق شهروندی",
        "مسئولیت‌پذیری", "راه‌حل سیاسی", "مذاکره",
    ],
    "moderate": [
        "معترضان", "کشته‌شدگان", "نیروهای امنیتی", "حقوق بشر",
        "شفافیت", "گزارش‌گر",
    ],
    "radical": [
        "قیام", "سرکوب", "کشتار", "رژیم", "رژیم ایران",
        "براندازی", "زندانی سیاسی", "جمهوری اسلامی",
    ],
}


def _compute_article_evidence(art: dict) -> dict:
    """Deterministic per-article bias features — no LLM.

    Counts loaded-word hits per subgroup, direct-quote markers (« »),
    and rough word count from the body. Used alongside the LLM
    neutrality score to make the number auditable.
    """
    text = (art.get("content") or "") + " " + (art.get("title") or "")
    hits: dict[str, int] = {}
    for subgroup, words in LOADED_WORDS_FA.items():
        c = 0
        for w in words:
            if not w:
                continue
            c += text.count(w)
        hits[subgroup] = c
    # Quote markers — Persian guillemet pair. Count matched pairs by
    # taking the min of opening/closing so unbalanced quotes don't
    # inflate the number.
    quote_open = text.count("«")
    quote_close = text.count("»")
    return {
        "loaded_hits": hits,
        "quote_count": min(quote_open, quote_close),
        "word_count": len(text.split()),
    }


def _narrative_group_from_dict(art: dict) -> str:
    """Derive a narrative subgroup from a plain article dict.

    Used when callers pass articles as dicts without a pre-populated
    `narrative_group` key. Uses the same rule as
    app.services.narrative_groups.narrative_group, fed with whatever
    fields the caller provided.
    """
    from types import SimpleNamespace
    shim = SimpleNamespace(
        production_location=art.get("production_location"),
        factional_alignment=art.get("factional_alignment"),
        state_alignment=art.get("state_alignment"),
    )
    return _narrative_group(shim)

STORY_ANALYSIS_PROMPT = """\
شما یک تحلیلگر ارشد رسانه‌ای هستید که برای پلتفرم شفافیت رسانه‌ای «دورنگر» کار می‌کنید. \
هدف: نشان دادن تفاوت‌های چارچوب‌بندی بین چهار زیرگروه رسانه‌های ایرانی — تا خواننده خودش قضاوت کند.

# تقسیم‌بندی رسانه‌ها (چهار زیرگروه در دو سمت)

درون‌مرزی (ایران):
  • اصول‌گرا — رسانه‌های حکومتی، سپاهی، یا مواضع اصول‌گرای جناحی
  • اصلاح‌طلب — رسانه‌های داخل کشور با گرایش اصلاحات یا جامعه مدنی

برون‌مرزی (دیاسپورا/خارج از ایران):
  • میانه‌رو — رسانه‌های عمومی بین‌المللی و مستقل (بی‌بی‌سی، دویچه‌وله، ایران‌وایر، هرانا…)
  • رادیکال — رسانه‌های تند اپوزیسیون یا سلطنت‌طلب (ایران اینترنشنال، کیهان لندن…)

# سبک نوشتار

- فارسی معیار و رسمی، نه محاوره‌ای.
- راوی بی‌طرف — از ادبیات هیچ طرفی استفاده نکنید.
- واژگان بارگذاری‌شده را فقط با گیومه «» نقل کنید.
- به شواهد عینی توجه کنید: ارقام، آمار، نام افراد، تاریخ‌ها، اسناد. این جزئیات را در عنوان و تحلیل بگنجانید.

# واژگان هر زیرگروه (نمونه، برای تشخیص لحن)

اصول‌گرا: فتنه، اغتشاش، شهید، مقاومت، دشمن، عوامل بیگانه، ضدانقلاب، تحریم ظالمانه
اصلاح‌طلب: اصلاحات، گفت‌وگو، جامعه مدنی، حقوق شهروندی، مسئولیت‌پذیری دولت، راه‌حل سیاسی
میانه‌رو: معترضان، کشته‌شدگان، نیروهای امنیتی، گزارش‌گونه، حقوق بشر، شفافیت
رادیکال: قیام، سرکوب، کشتار، رژیم ایران، براندازی، زندانی سیاسی

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

**قاعدهٔ مطلق — استناد فقط به رسانه‌های حاضر**: در تمام این تحلیل و در تمام متن‌های bias_explanation_fa، state_summary_fa، diaspora_summary_fa، independent_summary_fa، تنها نام رسانه‌هایی را می‌توانی بیاوری که در لیست مقالات بالا حضور دارند. اگر رسانه‌ای در بالا نیست، نه اسمش را بیاور نه به آن نسبت بده نه به محتوایش ارجاع بده. این قاعده خشک است و هیچ استثنایی ندارد. مثال: اگر در لیست بالا فقط «ایران اینترنشنال» و «بی‌بی‌سی فارسی» هستند، هرگز «پرس تی‌وی» یا «رادیو فردا» یا «تسنیم» را نام نبر — حتی اگر معمولاً در این موضوع می‌نویسند. اگر یک سمت (درون‌مرزی یا برون‌مرزی) هیچ مقاله‌ای در این خبر ندارد، بنویس که آن سمت پوشش نداده، نه اینکه ادعا کنی آن‌ها چه گفته‌اند.

**قاعدهٔ مطلقِ زیرگروه — سکوت را اختراع نکن**: همین قاعدهٔ حضور دقیقاً برای چهار زیرگروه (اصول‌گرا، اصلاح‌طلب، میانه‌رو، رادیکال) هم برقرار است. در لیست مقالات بالا برای هر مقاله «زیرگروه: …» مشخص شده. اگر هیچ مقاله‌ای در یک زیرگروه نبود، دربارهٔ آن زیرگروه هیچ ادعایی نکن — نه در bias_explanation_fa، نه در بولت‌های narrative، نه در state/diaspora_summary. ننویس «رسانه‌های رادیکال بر سرکوب تأکید کردند» وقتی هیچ مقالهٔ رادیکال در خبر نیست. به‌جای ادعا، سکوت را صریح بنویس («رسانه‌های رادیکال برون‌مرزی در این خبر حضور ندارند») یا آن زیرگروه را از متن حذف کن. همین قاعده خشک است.

**قاعدهٔ دوم — استناد فقط به محتوای مقالاتِ حاضر**: هر جمله و هر ادعا در state_summary_fa، diaspora_summary_fa، independent_summary_fa، و بولت‌های narrative باید مستقیماً از متنِ مقالاتِ همان سمت مشتق شده باشد — نه از الگوهای کلیشه‌ای که معمولاً این گروه مطرح می‌کند. مثال‌های ممنوع: اگر مقالات اصلاح‌طلب فقط دربارهٔ مذاکرات اسلام‌آباد حرف زده‌اند، ننویس «اصلاح‌طلبان بر دستاوردهای علمی و صنعتی تأکید کردند»؛ اگر مقالات حکومتی فقط شکست مذاکرات را گزارش کرده‌اند، ننویس «حکومتی‌ها از مقاومت مردمی ستایش کردند». هر مضمونی که در هیچ‌یک از مقالاتِ این سمت بیان نشده، در خلاصهٔ این سمت هم نباید بیاید — حتی اگر «در سیاست ایران معمولاً چنین می‌گویند». اگر یک سمت دربارهٔ یک جنبه سکوت کرده، سکوت را بنویس نه حدس.

bias_explanation_fa باید **عمیق، مشخص و بدون هم‌پوشانی** باشد. تعداد نکات را متناسب با حجم خبر تعیین کن:
- کمتر از ۱۰ مقاله → ۵ تا ۷ نکته
- بین ۱۰ تا ۳۰ مقاله → ۷ تا ۹ نکته
- بین ۳۰ تا ۶۰ مقاله → ۸ تا ۱۰ نکته
- بیش از ۶۰ مقاله → ۹ تا ۱۲ نکته

هر نکته یک جمله. با نقطه‌ویرگول (؛) جدا کن.

**قاعدهٔ ضد هم‌پوشانی (مهم):** هیچ دو نکته‌ای نباید یک چیز را بگویند. اگر دو نکته روی یک مشاهده تمرکز دارند (مثلاً هر دو دربارهٔ «واژگان هشداردهندهٔ حکومتی») آنها را ادغام کن و نکتهٔ دوم را برای مشاهدهٔ دیگری بگذار. هر نکته باید اطلاعاتی اضافه کند که در نکات قبلی نیامده.

هر نکته باید یکی از این الگوها را دنبال کند (و هر الگو حداکثر یک‌بار استفاده شود):
۱. چه چیزی حکومتی پنهان کرد / نادیده گرفت که اپوزیسیون پوشش داد (یا بالعکس)
۲. واژه‌ای بارگذاری‌شده که یک طرف استفاده کرد — با نقل مستقیم «»
۳. تفاوت لحن: پیروزمندانه vs هشداردهنده، سوگوار vs تهاجمی
۴. حقیقتی که یک طرف تحریف کرد یا بزرگ‌نمایی کرد — با ذکر ارقام و شواهد مشخص
۵. منبعی که یک طرف نقل کرد اما طرف دیگر نادیده گرفت
۶. تفاوت در ارائه آمار و ارقام — فقط وقتی هر دو طرف دربارهٔ **یک موضوع واحد** آمار داده‌اند (مثلاً هر دو دربارهٔ «تعداد تلفات حملات ۱۳ آوریل» حرف می‌زنند اما ارقام متفاوت می‌دهند). موضوع مشترک را صراحتاً نام ببر. اگر یکی از «مدت آتش‌بس» و دیگری از «مدت جنگ» صحبت می‌کند، مقایسه نکن — اینها دو موضوع متفاوتند حتی اگر هر دو عدد روز باشند
۷. تفاوت درون یک سمت — مثلاً اصول‌گرا در برابر اصلاح‌طلب، یا میانه‌رو در برابر رادیکال. نه فقط حکومتی در برابر اپوزیسیون
۸. منبعی که یک طرف به آن استناد کرده (رسمی/ناشناس/شاهد عینی) و تفاوت اعتبار آن با منبع سمت دیگر

هدف: خواننده‌ای که فقط bias_explanation را بخواند، باید ۴ تا ۸ مشاهدهٔ مجزا از پوشش خبری داشته باشد — نه دو بار تکرار یک مشاهده با عبارات مختلف.

# امتیاز اختلاف (dispute_score) — برای بخش «بیشترین اختلاف نظر» در صفحه اصلی
# 0.0 = هر دو طرف بر سر حقایق توافق دارند (فقط تفاوت لحن)
# 0.5 = اختلاف قابل‌توجه در چارچوب‌بندی و واقعیت‌های گزارش‌شده
# 1.0 = تناقض کامل — ادعاهای کاملاً متضاد، واقعیت‌های متفاوت

# واژگان بارگذاری‌شده (loaded_words) — برای بخش «واژه‌های هفته» در صفحه اصلی
# ۳ واژه یا عبارت بارگذاری‌شده‌ای که هر طرف در مقالاتش استفاده کرده
# مثلاً: conservative: ["پیروزی بزرگ", "محور مقاومت", "تسلیم دشمن"]
# مثلاً: opposition: ["آتش‌بس شکننده", "قطع اینترنت", "بحران انسانی"]

# خروجی

فقط JSON. بدون توضیح اضافی، بدون بلوک کد markdown.

{{
  "title_fa": "<تیتر خبری ۸-۱۲ کلمه — فقط جوهره رویداد: چه اتفاقی افتاد، کجا، چه ارقامی. هرگز از این واژه‌ها استفاده نکن: تحلیل، سوگیری، پوشش رسانه‌ای، روایت، بررسی، مقایسه، نقش عوامل خارجی. تیتر باید مثل روزنامه باشد نه عنوان پژوهش>",
  "title_en": "<English translation>",
  "summary_fa": "<۱-۲ جمله، ۲۰-۳۰ کلمه — فقط حقایق اصلی برای کارت صفحه اصلی>",
  "narrative": {{
    "inside": {{
      "principlist": ["<۲ تا ۳ بولت فارسی. هر بولت یک جمله کوتاه: رسانه‌های اصول‌گرا چه گفتند، چه واژگانی به‌کار بردند، چه چیزی را برجسته یا پنهان کردند>"],
      "reformist":   ["<۲ تا ۳ بولت فارسی برای رسانه‌های اصلاح‌طلب داخل ایران>"]
    }},
    "outside": {{
      "moderate":    ["<۲ تا ۳ بولت فارسی برای رسانه‌های میانه‌روی برون‌مرزی>"],
      "radical":     ["<۲ تا ۳ بولت فارسی برای رسانه‌های رادیکال برون‌مرزی>"]
    }}
  }},
  "state_summary_fa": "<۳-۴ جمله — **جوهر موضعِ این سمت**: چه می‌گویند، چه می‌خواهند، چه را برجسته می‌کنند، چه را پنهان. نام رسانه‌ها، عبارت «رسانه‌های حکومتی/درون‌مرزی»، یا «این سمت» را نیاور — خواننده می‌تواند با کلیک روی مقاله، بفهمد کدام رسانه چه گفت. فقط خودِ روایت. جمله‌ها باید مستقیم بیان موضع باشند («اقدام آمریکا غیرقانونی و زیاده‌خواهانه است»)، نه انتساب («حکومتی‌ها می‌گویند اقدام آمریکا غیرقانونی است»). یا null اگر هیچ رسانه‌ای از این سمت نباشد.>",
  "diaspora_summary_fa": "<۳-۴ جمله — **جوهر موضعِ این سمت**: همان قاعدهٔ بالا برای رسانه‌های برون‌مرزی. نام رسانه‌ها و برچسب «برون‌مرزی» نیاور، فقط روایت. یا null.>",
  "independent_summary_fa": null,
  "bias_explanation_fa": "<تعداد نکات متناسب با حجم مقالات (۵ تا ۱۲) با نقطه‌ویرگول (؛). هر نکته اطلاعات اضافه می‌کند — هیچ دو نکته‌ای هم‌پوشانی ندارند. نقل مستقیم واژگان با «» و ارقام مشخص. مقایسه بین دو سمت و بین زیرگروه‌ها.>",
  "scores": {{
    "state": {{"framing": ["حداکثر ۳ از: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"framing": ["حداکثر ۳"]}},
    "independent": {{"framing": ["حداکثر ۳"]}}
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
      "subgroup": "<یکی از: اصول‌گرا | اصلاح‌طلب | میانه‌رو | رادیکال>",
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
        _gr = art.get("narrative_group") or _narrative_group_from_dict(art)
        lines.append(f"منبع: {art.get('source_name_fa', '?')} — {SUBGROUP_LABELS_FA.get(_gr, 'نامشخص')}")
        lines.append(f"عنوان: {art.get('title', '')}")
        # Shorter content for nano — just first 800 chars
        content = (art.get("content", "") or "")[:800]
        if content:
            lines.append(f"متن: {content}")
        lines.append("")

    prompt = FACT_EXTRACTION_PROMPT.format(articles_block="\n".join(lines))

    try:
        from app.services.llm_helper import build_openai_params
        from app.services.llm_usage import log_llm_usage
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        params = build_openai_params(
            model=settings.translation_model,  # gpt-4.1-nano — cheapest
            prompt=prompt,
            max_tokens=2048,
            temperature=0,
        )
        response = await client.chat.completions.create(**params)
        await log_llm_usage(
            model=settings.translation_model,
            purpose="story_analysis.pass1_facts",
            usage=response.usage,
        )
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
            # New prompt emits `subgroup` but older cached facts might still
            # have `alignment`; accept either.
            align = fact.get("subgroup") or fact.get("alignment", "?")
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
        group = art.get("narrative_group") or _narrative_group_from_dict(art)
        subgroup_label = SUBGROUP_LABELS_FA.get(group, "نامشخص")
        source_name = art.get("source_name_fa", "نامشخص")
        title = art.get("title", "بدون عنوان")
        content = art.get("content", "")
        published = art.get("published_at") or ""

        lines.append(f"--- مقاله {i} ---")
        lines.append(f"عنوان: {title}")
        lines.append(f"منبع: {source_name} — زیرگروه: {subgroup_label}")
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
        from app.services.llm_usage import log_llm_usage

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        chosen_model = model or settings.story_analysis_model
        params = build_openai_params(
            model=chosen_model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        response = await client.chat.completions.create(**params)
        # Tier tag: premium vs baseline so the dashboard can show which
        # tier drove the spend without us re-parsing the model name.
        tier = "premium" if chosen_model == settings.story_analysis_premium_model else "baseline"
        await log_llm_usage(
            model=chosen_model,
            purpose=f"story_analysis.main.{tier}",
            usage=response.usage,
            story_id=story.id,
            meta={"include_analyst_factors": bool(include_analyst_factors)},
        )
        response_text = response.choices[0].message.content
        result = _parse_analysis_response(response_text)

        # Compute deterministic per-article evidence (loaded-word hits,
        # quote count, word count) so the local Claude audit can read
        # them directly without re-running the extractor. Neutrality
        # scores themselves are no longer produced by the LLM — they
        # come from scripts/neutrality_audit.py (Claude-scored).
        article_evidence: dict[str, dict] = {}
        for art in articles_with_sources:
            art_id = art.get("id")
            if not art_id:
                continue
            article_evidence[art_id] = _compute_article_evidence(art)

        result["article_evidence"] = article_evidence or None
        # Never overwrite an existing Claude-scored neutrality with the
        # LLM's (none) — the caller merges this with the story's prior
        # analysis blob.
        result.pop("article_neutrality", None)
        result.pop("source_neutrality", None)
        return result

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
        "narrative": None,
        "state_summary_fa": None,
        "diaspora_summary_fa": None,
        "independent_summary_fa": None,
        "bias_explanation_fa": None,
        "scores": None,
        "article_neutrality": None,
        "dispute_score": None,
        "loaded_words": None,
        "narrative_arc": None,
        "delta": None,
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    # If the LLM emitted structured bullets but forgot to synthesise the
    # legacy side summaries, build them ourselves by joining bullets.
    # This keeps any unmigrated frontend caller rendering content while
    # the migration rolls out.
    narr = result.get("narrative")
    if isinstance(narr, dict):
        if not result.get("state_summary_fa"):
            result["state_summary_fa"] = _join_side_bullets(narr.get("inside"))
        if not result.get("diaspora_summary_fa"):
            result["diaspora_summary_fa"] = _join_side_bullets(narr.get("outside"))

    return result


def _join_side_bullets(side: object) -> str | None:
    """Flatten `{subgroup: [bullets, ...], ...}` into a single Farsi paragraph."""
    if not isinstance(side, dict):
        return None
    parts: list[str] = []
    for _subgroup, bullets in side.items():
        if not isinstance(bullets, list):
            continue
        for b in bullets:
            if isinstance(b, str) and b.strip():
                parts.append(b.strip())
    if not parts:
        return None
    return " ".join(parts)

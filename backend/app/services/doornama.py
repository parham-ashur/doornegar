"""دورنما — narrative-synthesis briefing on top of the structured analysis.

Produces `briefing_fa`: a flowing 4-8 sentence Farsi prose explanation of
what's actually happening in a story — the kind of thing you'd say to a
smart friend who hasn't followed the news, integrating the per-side
narratives, the framing fault-line, and any silence patterns into a
single coherent paragraph.

Distinct from:
- `summary_fa` (neutral retelling of facts)
- `state_summary_fa` / `diaspora_summary_fa` (one-sided narratives)
- `bias_explanation_fa` (granular bias bullets)

دورنما is the integrative voice across all of those — the meta-narrative.

Runs after `story_analysis.generate_story_analysis` succeeds, only for
the top `settings.doornama_top_n` trending stories per pass. Skips
re-generation when the input fields haven't changed (briefing_hash
match), so unchanged top stories don't re-pay the LLM cost on every
maintenance pass.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


DOORNAMA_PROMPT = """\
تو راویِ «دورنما» در دورنگر هستی. وظیفه‌ات نوشتن یک پاراگراف تحلیلی منسجم \
دربارهٔ یک خبر است — به این شکل که اگر کسی کلِ صفحهٔ خبر را خوانده باشد \
و بخواهد در ۴ تا ۸ جملهٔ روان به یک دوستِ ناآگاه توضیح دهد «در واقع چه \
دارد می‌گذرد»، چه می‌گوید.

دورنما خلاصهٔ خبر نیست (آن کار صفحهٔ مقاله است)، فهرست سوگیری‌ها هم نیست \
(آن کار bias_explanation است)، روایتِ یک‌سمتی هم نیست. دورنما یک متنِ \
یکپارچه‌ است که سه چیز را کنار هم می‌بافد:
  ۱. خودِ رویداد در یک جملهٔ کوتاه (چه شد؟)
  ۲. شکافِ چارچوب‌بندی — هر سمت این رویداد را در چه قابی قرار می‌دهد، \
     چرا آن قاب برایش اهمیت دارد، و این دو قاب کجا با هم اصطکاک دارند
  ۳. آنچه گفته نشده — یک سمت دربارهٔ چه چیزی سکوت کرده، یا چه زاویه‌ای \
     در پوشش غایب است

# قواعد لحن
- لحن: راویِ کنجکاوِ توضیح‌گر. نه گزارش‌گون («دو طرف نظر متفاوتی دارند»)، \
  نه روزنامه‌نگاری مقاله‌ای («واضح است که حکومت...»). یک نفر که اطلاعات را \
  هضم کرده و در حال هضم‌کردنِ آن برای دیگری است.
- ساختار: یک پاراگراف پیوسته. **بدون بولت، بدون فهرست، بدون عناوین.** \
  جمله‌های متوسط تا بلند، با پل‌زدن بین ایده‌ها («اما اگر هر دو سمت را \
  کنار هم بگذاری...»، «نکتهٔ ظریف اینجاست که...»).
- حجم: ۴ تا ۸ جمله. حداکثر حدود ۶۰۰ حرف. خلاصه‌نویسی، نه گسترش.
- شخصِ راوی: راوی هیچ‌کدام از دو سمت نیست. حتی وقتی یک سمت آشکارا تحریف \
  می‌کند، بنویس «این سمت چنین قاب‌بندی می‌کند»، نه «این سمت دروغ می‌گوید».

# قواعد محتوا (سخت‌گیرانه)
- استناد فقط به محتوای ورودی. هیچ ادعا یا تفسیری که در state_summary, \
  diaspora_summary, bias_explanation, silence_analysis, narrative_arc \
  ورودی نیست را در دورنما نیاور.
- اگر یک سمت در این خبر حضور ندارد، در دورنما هم آن سمت را به‌عنوان \
  حاضر فرض نکن — صراحتاً اشاره کن که آن سمت سکوت کرده یا پوشش نداده.
- نام رسانه‌ها را در دورنما نیاور (آن جزئیات در صفحهٔ خبر هست). به‌جای \
  «ایران اینترنشنال گفت» بنویس «روایت برون‌مرزی تأکید دارد که...».
- اعداد و ارقام مشخص (تعداد کشته، درصد رأی) را اگر در ورودی هست، در \
  دورنما هم نگه دار. اگر نیست، نساز.

# لنگرگاه ویرایش سردبیر (اختیاری)
{anchor_block}

# ورودی — اطلاعات تحلیل خبر
عنوان خبر: {title_fa}

روایت درون‌مرزی (state_summary_fa):
{state_summary}

روایت برون‌مرزی (diaspora_summary_fa):
{diaspora_summary}

روایت مستقل (independent_summary_fa، اگر موجود):
{independent_summary}

تحلیل سوگیری و چارچوب‌بندی (bias_explanation_fa):
{bias_explanation}

تحلیل سکوت (کدام سمت دربارهٔ چه چیزی سکوت کرده، اگر موجود):
{silence_analysis}

قوس روایت (تحول داستان در طول زمان، اگر موجود):
{narrative_arc}

# خروجی
دقیقاً یک پاراگراف فارسی روان. بدون پیشوند، بدون عنوان، بدون JSON. \
فقط متنِ خامِ پاراگراف. شروع نکن با «این خبر دربارهٔ...» یا «خلاصه...» \
— مستقیم وارد روایت شو.
"""


def _format_input_field(value: Any) -> str:
    """Render a structured field (str | dict | list | None) for the prompt."""
    if value is None or value == "":
        return "ندارد."
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        import json as _json
        try:
            return _json.dumps(value, ensure_ascii=False, indent=2)[:1500]
        except Exception:
            return str(value)[:1500]
    return str(value)[:1500]


def compute_briefing_hash(
    *,
    state_summary_fa: str | None,
    diaspora_summary_fa: str | None,
    independent_summary_fa: str | None,
    bias_explanation_fa: str | None,
    silence_analysis: Any = None,
    narrative_arc: Any = None,
) -> str:
    """Stable hash of the inputs دورنما reads. Identical hash → skip LLM."""
    import json as _json

    payload = {
        "state": state_summary_fa or "",
        "diaspora": diaspora_summary_fa or "",
        "independent": independent_summary_fa or "",
        "bias": bias_explanation_fa or "",
        "silence": _json.dumps(silence_analysis, ensure_ascii=False, sort_keys=True)
        if silence_analysis is not None else "",
        "arc": _json.dumps(narrative_arc, ensure_ascii=False, sort_keys=True)
        if narrative_arc is not None else "",
    }
    blob = _json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


async def generate_doornama_briefing(
    *,
    story_id: str,
    title_fa: str | None,
    state_summary_fa: str | None,
    diaspora_summary_fa: str | None,
    independent_summary_fa: str | None,
    bias_explanation_fa: str | None,
    silence_analysis: Any = None,
    narrative_arc: Any = None,
    summary_anchor_briefing_fa: str | None = None,
) -> dict | None:
    """Generate the دورنما briefing paragraph.

    Returns `{"briefing_fa": str, "briefing_hash": str}` on success,
    `None` on any failure (no silent fallback — caller decides whether
    to retry on the next pass).
    """
    if not settings.openai_api_key:
        logger.warning("doornama: skipping (no openai_api_key)")
        return None

    if not (state_summary_fa or diaspora_summary_fa or bias_explanation_fa):
        logger.info("doornama: skipping story=%s (no narrative inputs yet)", story_id)
        return None

    anchor_block = "ندارد."
    if summary_anchor_briefing_fa:
        anchor_block = (
            "سردبیر دورنگر این پاراگراف دورنما را قبلاً ویرایش کرده. لحن، "
            "ساختار جمله و ترتیب نکات را تا حد ممکن نگه دار. اگر اطلاعات "
            "تازه‌ای در ورودی هست که در نسخهٔ سردبیر منعکس نشده، آن را "
            "هوشمندانه با لنگرگاه ادغام کن:\n"
            f"  {summary_anchor_briefing_fa[:600]}"
        )

    prompt = DOORNAMA_PROMPT.format(
        anchor_block=anchor_block,
        title_fa=title_fa or "بدون عنوان",
        state_summary=_format_input_field(state_summary_fa),
        diaspora_summary=_format_input_field(diaspora_summary_fa),
        independent_summary=_format_input_field(independent_summary_fa),
        bias_explanation=_format_input_field(bias_explanation_fa),
        silence_analysis=_format_input_field(silence_analysis),
        narrative_arc=_format_input_field(narrative_arc),
    )

    try:
        import openai
        from app.services.llm_helper import build_openai_params
        from app.services.llm_usage import log_llm_usage

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        params = build_openai_params(
            model=settings.doornama_model,
            prompt=prompt,
            max_tokens=800,
        )
        response = await client.chat.completions.create(**params)
        text = (response.choices[0].message.content or "").strip()

        # Strip occasional markdown fences / leading labels the model
        # sometimes ignores the prompt and adds.
        for prefix in ("```", "متن:", "پاراگراف:", "دورنما:"):
            if text.startswith(prefix):
                text = text.split("\n", 1)[1] if "\n" in text else text[len(prefix):]
                text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        await log_llm_usage(
            model=settings.doornama_model,
            purpose="doornama",
            usage=response.usage,
            story_id=story_id,
        )

        if not text:
            logger.warning("doornama: empty completion for story=%s", story_id)
            return None

        briefing_hash = compute_briefing_hash(
            state_summary_fa=state_summary_fa,
            diaspora_summary_fa=diaspora_summary_fa,
            independent_summary_fa=independent_summary_fa,
            bias_explanation_fa=bias_explanation_fa,
            silence_analysis=silence_analysis,
            narrative_arc=narrative_arc,
        )
        return {"briefing_fa": text, "briefing_hash": briefing_hash}

    except Exception as e:
        logger.warning("doornama: generation failed for story=%s: %s", story_id, e)
        return None

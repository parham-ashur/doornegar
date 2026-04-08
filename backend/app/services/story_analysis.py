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
تو تحلیلگر رسانه‌ای هستی. مقالات زیر درباره یک رویداد خبری ایرانی هستند.

مقالات:
{articles_block}

خروجی: فقط JSON. مختصر و دقیق بنویس.

{{
  "summary_fa": "خلاصه رویداد در ۳-۴ جمله. فقط حقایق. بدون سوال.",
  "state_summary_fa": "دیدگاه رسانه‌های حکومتی در ۲-۳ جمله. چه تأکیدی دارند؟ اگر موجود نیست: null",
  "diaspora_summary_fa": "دیدگاه رسانه‌های برون‌مرزی در ۲-۳ جمله. چه تفاوتی دارد؟ اگر موجود نیست: null",
  "independent_summary_fa": "دیدگاه مستقل در ۲-۳ جمله. اگر موجود نیست: null",
  "bias_explanation_fa": "مقایسه مختصر تفاوت چارچوب‌بندی و لحن بین طرف‌ها در ۲-۳ جمله.",
  "scores": {{
    "state": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["از این لیست انتخاب کن: مقاومت، پیروزی، قربانی، تهدید، بحران، امنیت، حقوق بشر، اقتصادی، دخالت خارجی، خنثی"]}},
    "diaspora": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["..."]}},
    "independent": {{"tone": -2تا2, "factuality": 1تا5, "emotional_language": 1تا5, "framing": ["..."]}}
  }}
}}

قوانین: مختصر باش. هر بخش حداکثر ۳ جمله. بر اساس متن واقعی مقالات. اگر دسته‌ای نیست، null بگذار. فقط JSON."""


async def generate_story_analysis(
    story,
    articles_with_sources: list[dict],
) -> dict:
    """Generate rich analysis for a story using article content.

    Args:
        story: The Story ORM object.
        articles_with_sources: List of dicts with keys:
            title, content, source_name_fa, state_alignment

    Returns:
        dict with keys: summary_fa, state_summary_fa, diaspora_summary_fa,
        independent_summary_fa, bias_explanation_fa, scores
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in .env to use story analysis."
        )

    # Build articles block with content
    lines = []
    for i, art in enumerate(articles_with_sources, 1):
        alignment_fa = ALIGNMENT_LABELS_FA.get(
            art.get("state_alignment", ""), "نامشخص"
        )
        source_name = art.get("source_name_fa", "نامشخص")
        title = art.get("title", "بدون عنوان")
        content = art.get("content", "")

        lines.append(f"--- مقاله {i} ---")
        lines.append(f"عنوان: {title}")
        lines.append(f"منبع: {source_name} (جهت‌گیری: {alignment_fa})")
        if content:
            lines.append(f"متن: {content}")
        lines.append("")

    articles_block = "\n".join(lines)

    prompt = STORY_ANALYSIS_PROMPT.format(articles_block=articles_block)

    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
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

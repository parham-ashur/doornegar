"""Grab-bag detector — an LLM that reads article titles to judge cluster coherence.

A 'grab-bag' is a cluster whose title names one topic but whose articles are
about several *different events* that merely share embedding-space proximity
(e.g. «فرهنگیان بازنشسته» / retired educators, but the articles were drugs /
mine protest / singer arrest / nurses / Green Movement).

Embedding geometry CANNOT detect this — embeddings encode topic/domain
similarity, not event identity, so a grab-bag of generically-similar Persian
domestic-news articles sits tighter around its centroid than a rich coherent
story does (validated 2026-06-20: grab-bags scored HIGHER than coherent
stories on mean-cosine-to-centroid). See memory project_grabbag_detection.md.

The reliable signal is what a human auditor (Niloofar) uses: READ the titles.
This module asks gpt-4.1-nano: "what single news event do the most headlines
share, and how many of them share it?" If the largest shared-event group is
under HALF the articles, the cluster is a grab-bag.

Cheap by design: titles only (no bodies), ~5-8 calls per cron, gpt-4.1-nano.
Runs BEFORE the per-story summarize/bias spend, so it SAVES net LLM by killing
grab-bags before they're expensively analyzed.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# ── tunables ──────────────────────────────────────────────────────────────────
# Archive if the largest shared-event group is below this fraction.
# Calibrated 2026-06-20 against a labeled set: grab-bags scored 10-40%
# on-topic, coherent stories 50-67%. 0.45 sits in the dead-zone between
# them — catches every grab-bag (internet @ 40%) while leaving a 5-point
# margin below the lowest coherent story (iran-2-nuclear @ 50%), so it's
# robust to ±1 count noise from the judge.
MIN_ON_TOPIC_FRACTION = 0.45
MIN_ARTICLE_COUNT = 5         # below this, too small to judge as a cluster
MAX_ARTICLE_COUNT = 25        # above this, almost always a real well-covered event
MAX_TITLES_IN_PROMPT = 25     # cap prompt size
MAX_AGE_HOURS = 48            # only gate fresh clusters; old ones are stable
SAFETY_CAP = 5                # never archive more than this per run (drift backstop)
PIN_FLOOR = 1                 # priority >= PIN_FLOOR = pinned → always exempt


_JUDGE_PROMPT = """\
You are auditing the coherence of a news-story cluster for an Iranian news
aggregator. A good cluster is a set of articles all reporting the SAME news
event. A bad cluster ("grab-bag") bundles articles about DIFFERENT, unrelated
events that just happen to be domestic Iranian news.

Below is the cluster's current title and a numbered list of its article
headlines. Ignore the title if it is misleading — judge by the headlines.

Identify the SINGLE news event that the LARGEST number of these headlines are
about. Count how many headlines are about that one event. Headlines about a
different event, or generic/unrelated items, do NOT count.

Return ONLY a JSON object (no prose, no markdown fences). Keep it short — for
off_topic_indices give the HEADLINE NUMBERS only, never the text:
  {{"dominant_event": "<short description in English, <=10 words>",
    "on_topic_count": <int>,
    "total": <int>,
    "off_topic_indices": [<int>, ...]}}

Cluster title: {title}

Headlines:
{headlines}
"""


def build_judge_prompt(story_title: str, article_titles: list[str]) -> str:
    titles = article_titles[:MAX_TITLES_IN_PROMPT]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    return _JUDGE_PROMPT.format(title=story_title or "(untitled)", headlines=numbered)


def parse_judge_response(raw: str, total_sent: int) -> dict | None:
    """Parse the judge's JSON. Returns dict with on_topic_count/total/
    dominant_event, or None on unparseable output (caller treats None as
    'skip' — never archive on a parse failure)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            logger.warning("coherence_judge: unparseable response: %s", (raw or "")[:200])
            return None
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("coherence_judge: malformed JSON: %s", (raw or "")[:200])
            return None
    if not isinstance(obj, dict):
        return None
    try:
        on_topic = int(obj.get("on_topic_count"))
    except (TypeError, ValueError):
        return None
    # Trust the count of titles we actually sent over the model's echoed total.
    total = total_sent
    on_topic = max(0, min(on_topic, total))
    return {
        "dominant_event": str(obj.get("dominant_event") or "")[:200],
        "on_topic_count": on_topic,
        "total": total,
        "off_topic_indices": obj.get("off_topic_indices") if isinstance(
            obj.get("off_topic_indices"), list
        ) else [],
    }


def is_grab_bag(parsed: dict | None) -> bool:
    """True when the largest shared-event group is below MIN_ON_TOPIC_FRACTION."""
    if not parsed:
        return False
    total = parsed.get("total") or 0
    if total < MIN_ARTICLE_COUNT:
        return False
    fraction = parsed["on_topic_count"] / total
    return fraction < MIN_ON_TOPIC_FRACTION


async def _call_judge(prompt: str) -> str:
    """Call gpt-4.1-nano for the coherence judgment + log usage.

    Mirrors content_type._call_openai_classify. Tests patch this to bypass
    the network."""
    import openai

    from app.config import settings
    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.content_type_model,
        prompt=prompt,
        max_tokens=400,
        temperature=0,
    )
    response = await client.chat.completions.create(**params)
    await log_llm_usage(
        model=settings.content_type_model,
        purpose="maintenance.coherence_gate",
        usage=response.usage,
    )
    return response.choices[0].message.content or ""


async def judge_story(story_title: str, article_titles: list[str]) -> dict | None:
    """Judge one story. Returns parsed dict (with on_topic_count/total/
    dominant_event) or None on failure. Never raises — a judge failure must
    not crash the maintenance step or cause an archive."""
    from app.config import settings

    titles = [t for t in article_titles if t and t.strip()][:MAX_TITLES_IN_PROMPT]
    if len(titles) < MIN_ARTICLE_COUNT:
        return None
    if not settings.openai_api_key:
        logger.warning("coherence_judge: OPENAI_API_KEY not set — skipping")
        return None
    prompt = build_judge_prompt(story_title, titles)
    try:
        raw = await _call_judge(prompt)
    except Exception as e:
        logger.warning("coherence_judge: LLM call failed: %s", e)
        return None
    return parse_judge_response(raw, total_sent=len(titles))

"""Bellwether / missing-main-story check.

The one failure mode our internal canaries CAN'T catch: a major story we never
ingested at all (so it isn't in our data to flag). The manual fix has been the
chat-driven bellwether ritual (read a few balanced outlet homepages, notice the
lead we missed, seed+pin it — reference_bellwether_outlet_check). This automates
the DETECTION half: fetch a few bellwether outlets, ask a cheap LLM whether a
story prominent across them is missing from our top homepage stories, and log
the verdict. A canary reads the latest verdict; the morning briefing surfaces it.
The ACTION (seed+pin) stays editorial/manual — this only raises the flag.

Reachability caveat: fetched from Railway (US). Diaspora outlets (Iran
International, London) are reliably reachable; some inside-Iran state sites may
geo-block US IPs. The check fails gracefully per-outlet and the canary reports
"stale/unable" when nothing was reachable — it never fails the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.story import Story

logger = logging.getLogger(__name__)

# (key, homepage URL). Diaspora-first because those are reachable from Railway;
# inside-Iran ones are best-effort and may be geo-blocked (handled gracefully).
DEFAULT_OUTLETS: list[tuple[str, str]] = [
    ("iran_international", "https://www.iranintl.com/"),
    ("bbc_persian", "https://www.bbc.com/persian"),
    ("mehr", "https://www.mehrnews.com/"),
    ("etemad", "https://www.etemadonline.com/"),
]

_HEADLINE_RE = re.compile(
    r"<(?:title|h1|h2|h3)\b[^>]*>(.*?)</(?:title|h1|h2|h3)>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

EVENT_TYPE = "bellwether_check"


def _extract_headlines(html: str, limit: int = 15) -> list[str]:
    """Pull <title>/<h1>/<h2>/<h3> text from a homepage — that's where lead
    headlines live — without an LLM call. Cheap, robust to layout changes."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _HEADLINE_RE.finditer(html):
        txt = _WS_RE.sub(" ", _TAG_RE.sub("", m.group(1))).strip()
        if 12 <= len(txt) <= 160 and txt not in seen:
            seen.add(txt)
            out.append(txt)
        if len(out) >= limit:
            break
    return out


async def _fetch_outlet(client: httpx.AsyncClient, url: str) -> list[str] | None:
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        return _extract_headlines(r.text)
    except Exception as e:  # geo-block, timeout, 4xx/5xx — all non-fatal
        logger.info("bellwether: %s unreachable (%s)", url, type(e).__name__)
        return None


async def _our_top_titles(
    db: AsyncSession, limit: int = 12, fresh_days: int = 4, fresh_limit: int = 40
) -> list[str]:
    """Titles the comparator checks an outlet lead against.

    The prompt says a story counts as covered if we have ANYTHING on the same
    event — so this must reflect our *coverage*, not just our most prominent
    slice. Two parts, unioned:
      1. top-`limit` by priority (what's prominent on the homepage), and
      2. all fresh stories (≤ fresh_days) regardless of priority.

    Part 2 fixes a real false-positive (observed 2026-06-03): demoted war
    clusters (priority = -50, e.g. "Iran missile attacks on US bases") sort
    below the top-12 by priority, so the LLM never saw them and reported the
    event MISSING even though we covered it twice. Demoted ≠ absent.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=fresh_days)
    prominent = (await db.execute(
        select(Story.title_fa)
        .where(Story.archived_at.is_(None), Story.article_count >= 5)
        .order_by(Story.priority.desc(), Story.trending_score.desc())
        .limit(limit)
    )).scalars().all()
    fresh = (await db.execute(
        select(Story.title_fa)
        .where(
            Story.archived_at.is_(None),
            Story.article_count >= 5,
            Story.first_published_at >= cutoff,
        )
        .order_by(Story.trending_score.desc())
        .limit(fresh_limit)
    )).scalars().all()
    # Preserve order (prominent first), dedup.
    seen: set[str] = set()
    out: list[str] = []
    for t in [*prominent, *fresh]:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


_COMPARE_PROMPT = """\
You audit an Iran-focused news aggregator for COVERAGE GAPS.

Below are front-page headlines from major outlets, then the aggregator's current
top stories. Decide if there is a MAJOR Iran-related story (politics, conflict,
economy, foreign relations, human rights) that is prominent across the OUTLETS
but is MISSING from the aggregator's top stories. Ignore sports, weather,
entertainment, and minor/local items. A story counts as covered if the
aggregator has anything on the same event, even if worded differently.

Return ONLY JSON: {{"missing": <bool>, "missed_story": "<short FA description or empty>", "confidence": <0-1>}}

=== OUTLET FRONT-PAGE HEADLINES ===
{outlets}

=== AGGREGATOR TOP STORIES ===
{ours}
"""


async def _llm_compare(outlets_block: str, ours_block: str) -> dict | None:
    if not settings.openai_api_key:
        return None
    import openai
    from app.services.llm_helper import build_openai_params
    from app.services.llm_usage import log_llm_usage

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.content_type_model,  # gpt-4.1-nano — cheap
        prompt=_COMPARE_PROMPT.format(outlets=outlets_block, ours=ours_block),
        max_tokens=200,
        temperature=0,
    )
    try:
        resp = await client.chat.completions.create(**params)
        await log_llm_usage(
            model=settings.content_type_model, purpose="bellwether", usage=resp.usage
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[4:].lstrip() if raw[:4].lower() == "json" else raw
            raw = raw.split("```", 1)[0]
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group(0)) if m else None
    except Exception as e:
        logger.warning("bellwether LLM compare failed: %s", e)
        return None


async def run_bellwether_check(db: AsyncSession) -> dict[str, Any]:
    """Fetch bellwether outlets, compare lead headlines to our top stories, log
    the verdict. Non-fatal throughout. Returns the verdict dict."""
    now = datetime.now(timezone.utc)
    reachable: dict[str, list[str]] = {}
    failed: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DoornegarBellwether/1.0)"}
    async with httpx.AsyncClient(headers=headers) as client:
        for key, url in DEFAULT_OUTLETS:
            heads = await _fetch_outlet(client, url)
            if heads:
                reachable[key] = heads
            else:
                failed.append(key)

    result: dict[str, Any] = {
        "checked_at": now.isoformat(),
        "outlets_reachable": list(reachable.keys()),
        "outlets_failed": failed,
        "missing": False,
        "missed_story": "",
        "confidence": 0.0,
        "status": "ok",
    }

    if not reachable:
        result["status"] = "unable"  # nothing fetchable — canary reports stale
    else:
        ours = await _our_top_titles(db)
        outlets_block = "\n".join(
            f"[{k}]\n" + "\n".join(f"- {h}" for h in hs[:10])
            for k, hs in reachable.items()
        )
        ours_block = "\n".join(f"- {t}" for t in ours) or "(none)"
        verdict = await _llm_compare(outlets_block, ours_block)
        if verdict is None:
            result["status"] = "unable"  # no key / LLM failed
        else:
            result["missing"] = bool(verdict.get("missing"))
            result["missed_story"] = str(verdict.get("missed_story") or "")[:300]
            try:
                result["confidence"] = max(0.0, min(1.0, float(verdict.get("confidence", 0))))
            except (TypeError, ValueError):
                result["confidence"] = 0.0

    try:
        from app.services.events import log_event
        await log_event(db, event_type=EVENT_TYPE, actor="cron", signals=result)
        await db.commit()
    except Exception as e:
        logger.warning("bellwether: failed to log event: %s", e)

    logger.info("bellwether check: %s", {k: result[k] for k in ("missing", "missed_story", "outlets_reachable", "status")})
    return result

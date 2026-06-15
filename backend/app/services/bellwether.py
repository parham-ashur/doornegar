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

# Sports / entertainment noise. The comparator prompt already says "ignore
# sports", but a homepage's <h2>/<h3> often LEAD with football during a
# tournament (observed 2026-06-14: Iran International's top headlines were all
# World Cup — کوراسائو، فیفا، ورزشگاه — which pushed the real Iran-US lead out
# of the top-10 slice we feed the LLM and produced a false "missing" flag).
# Drop these at extraction so the real political/conflict leads survive.
_NOISE_RE = re.compile(
    r"جام جهانی|فوتبال|فیفا|ورزشگاه|والیبال|بسکتبال|المپیک|لیگ برتر"
    r"|دروازه‌?بان|هافبک|گلزنی|باشگاه|سرمربی|قلعه‌نویی|تیم ملی فوتبال"
    r"|جشنواره فیلم|باکس آفیس|اسکار|کنسرت"
)
# Site chrome / section labels that aren't stories (nav, masthead, "live").
_NAV_RE = re.compile(
    r"^(?:صفحه اصلی|صفحه اول|خبرهای? کوتاه|مهم?ترین خبرها?|آخرین اخبار"
    r"|تازه‌ترین|BBC News|ایران اینترنشنال|پربیننده‌ترین)\b"
    r"|^BBC News|اینترنشنال$"
)


def _is_noise_headline(txt: str) -> bool:
    return bool(_NOISE_RE.search(txt) or _NAV_RE.search(txt))


_PUNCT_RE = re.compile(r"[؛،:.!؟…\-«»\"'‌]")


def _norm_title(s: str) -> str:
    """Normalize a title for matching: unify Arabic/Persian glyph variants,
    drop punctuation + zero-width joiners, collapse whitespace."""
    s = (s or "").replace("ي", "ی").replace("ك", "ک")
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _closest_matches_ours(closest: str, ours: list[str]) -> bool:
    """True when the LLM's `closest_existing` is really one of OUR titles.

    The comparator (gpt-4.1-nano) is told to name the nearest same-event
    aggregator title before deciding `missing`, then only flag missing when NO
    title covers the event. Observed 2026-06-15: it named an EXACT match
    («…۱۱ موشک به سمت تل‌آویو…», #13 in our own list) yet still returned
    missing=true — a self-contradiction the nano model won't reliably avoid.
    So we don't trust its boolean over its own evidence: if `closest_existing`
    strongly overlaps a compared title, the event IS covered. Strong = ≥4
    shared tokens AND ≥60% overlap in either direction (the echoed title may be
    lightly reworded or truncated)."""
    c = set(_norm_title(closest).split())
    if len(c) < 3:
        return False
    for t in ours:
        o = set(_norm_title(t).split())
        if not o:
            continue
        inter = len(c & o)
        if inter >= 4 and (inter / len(c) >= 0.6 or inter / len(o) >= 0.6):
            return True
    return False


def _extract_headlines(html: str, limit: int = 15) -> list[str]:
    """Pull <title>/<h1>/<h2>/<h3> text from a homepage — that's where lead
    headlines live — without an LLM call. Cheap, robust to layout changes.
    Sports/entertainment + site-chrome lines are dropped so a tournament
    week's football headlines don't crowd out the real political lead."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _HEADLINE_RE.finditer(html):
        txt = _WS_RE.sub(" ", _TAG_RE.sub("", m.group(1))).strip()
        if 12 <= len(txt) <= 160 and txt not in seen and not _is_noise_headline(txt):
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

DECISION PROCEDURE — follow exactly, it prevents false alarms:
1. Pick the single most prominent MAJOR Iran story across the OUTLET headlines.
2. Scan the AGGREGATOR TOP STORIES and name the ONE title closest to it
   (`closest_existing`). Same event counts even if the wording, angle, or
   sub-detail differs (e.g. an outlet leads on "protests against the deal" and
   the aggregator has "the deal" — that is COVERED; a deal and its fallout are
   the SAME event).
3. Only set missing=true if NO aggregator title plausibly covers that event.
   When the closest title is on the same broad event, set missing=FALSE.
   Bias toward missing=false on doubt — a false alarm is worse than a miss.

Return ONLY JSON:
{{"missing": <bool>, "missed_story": "<short FA description or empty>",
  "closest_existing": "<the nearest aggregator title you found, or empty>",
  "confidence": <0-1>}}

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
        "closest_existing": "",
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
        # Evidence for the verdict. Without it a `missing=true conf 0.9`
        # flag is un-actionable: nobody can tell whether it's a real gap or
        # the comparator failing to credit an umbrella story for a sub-angle
        # (observed 2026-06-14: outlets led with the hardliner backlash to
        # the Geneva deal, which we covered as one umbrella hero — the LLM
        # read the backlash as a "missing" lead). Persisting the lead
        # headlines it saw + the titles it compared against makes every
        # flag judgeable at a glance from the logged event. Capped to keep
        # the signals blob small.
        result["outlet_leads"] = {
            k: hs[:6] for k, hs in reachable.items()
        }
        result["compared_titles"] = ours[:15]
        verdict = await _llm_compare(outlets_block, ours_block)
        if verdict is None:
            result["status"] = "unable"  # no key / LLM failed
        else:
            result["missing"] = bool(verdict.get("missing"))
            result["missed_story"] = str(verdict.get("missed_story") or "")[:300]
            # The title the LLM judged closest — its own justification for the
            # verdict. On a missing=true flag this shows whether it genuinely
            # found no match or just under-credited an existing umbrella story.
            result["closest_existing"] = str(verdict.get("closest_existing") or "")[:300]
            try:
                result["confidence"] = max(0.0, min(1.0, float(verdict.get("confidence", 0))))
            except (TypeError, ValueError):
                result["confidence"] = 0.0
            # Deterministic guardrail against the nano model's self-
            # contradiction (named an exact match, still said missing=true).
            # If its own closest_existing really is one of our titles, the
            # event is covered — suppress the flag and record why.
            if result["missing"] and _closest_matches_ours(result["closest_existing"], ours):
                result["missing"] = False
                result["missing_override"] = (
                    "closest_existing matched a compared title — "
                    "LLM self-contradiction suppressed"
                )

    try:
        from app.services.events import log_event
        await log_event(db, event_type=EVENT_TYPE, actor="cron", signals=result)
        await db.commit()
    except Exception as e:
        logger.warning("bellwether: failed to log event: %s", e)

    logger.info("bellwether check: %s", {k: result[k] for k in ("missing", "missed_story", "outlets_reachable", "status")})
    return result

"""Incident ledger + self-review packet — the C3 "learn from mistakes" loop.

Parham 2026-06-03 ([[feedback_iterative_prompt_improvement]]): the goal is a
self-running FA product whose quality *rises* over time. Canaries DETECT drift;
the bellwether catches missed stories; regression cases LOCK fixes. The missing
piece was a durable record of *what broke and why*, so each defect can be mapped
back to the responsible prompt/step and turned into a permanent fix.

This module is that record. An "incident" is one real defect — found by a
canary, by Parham, or during a Niloofar audit — stored as a `story_events` row
(event_type='incident', detail in `signals`). No new table: story_events already
has a nullable story_id, an indexed event_type, and a JSONB signals column.

The companion `self_review_packet()` assembles everything a periodic review
needs in one read: the current non-ok canaries, the open incidents, and recent
maintenance fails. The review RITUAL (run in chat, no LLM spend) is:
  1. read the packet,
  2. map each non-ok canary / recent fail to the responsible prompt or step,
  3. for anything not already tracked, log_incident() it,
  4. propose a versioned prompt/step edit + a golden case in
     tests/test_regression_cases.py,
  5. mark incidents fixed once the regression case is green.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_event import StoryEvent
from app.services.events import log_event

INCIDENT_EVENT = "incident"

# status lifecycle: open -> monitoring -> fixed (or wontfix)
_STATUSES = ("open", "monitoring", "fixed", "wontfix")
_SEVERITIES = ("low", "med", "high")
# WHO/WHAT first surfaced the defect — the input to the Human-Intervention Rate
# (HIR) North-Star metric. `human` = Parham caught it by eye (the thing we want
# to drive to zero); `canary`/`self_heal` = an automated signal caught it first
# (what a self-running product should do); `audit` = a Niloofar/review pass.
_DETECTORS = ("canary", "self_heal", "audit", "human", "claude", "unknown")


async def log_incident(
    db: AsyncSession,
    *,
    slug: str,
    title: str,
    symptom: str,
    root_cause: str,
    responsible: str,
    fix: str | None = None,
    regression_case: str | None = None,
    severity: str = "med",
    status: str = "open",
    detected_by: str = "unknown",
    actor: str = "claude",
    commit: bool = False,
) -> None:
    """Record one defect. `slug` is a stable human key (kebab-case) used to
    dedup — re-logging the same slug appends a new row (history), so prefer
    updating status via a fresh row with the same slug.

    `responsible` names the prompt/step/file at fault (e.g.
    'bellwether._our_top_titles', 'content_type heuristic', 'clustering
    pinned-umbrella accretion'). That mapping is the whole point — it's what
    turns "a canary went red" into "this prompt needs an edit".
    """
    if severity not in _SEVERITIES:
        severity = "med"
    if status not in _STATUSES:
        status = "open"
    if detected_by not in _DETECTORS:
        detected_by = "unknown"
    await log_event(
        db,
        event_type=INCIDENT_EVENT,
        actor=actor,
        signals={
            "slug": slug,
            "title": title,
            "symptom": symptom,
            "root_cause": root_cause,
            "responsible": responsible,
            "fix": fix,
            "regression_case": regression_case,
            "severity": severity,
            "status": status,
            "detected_by": detected_by,
        },
        commit=commit,
    )


async def list_incidents(
    db: AsyncSession, *, limit: int = 50, include_fixed: bool = True
) -> list[dict[str, Any]]:
    """Most-recent incidents first. Each row's `signals` is flattened up with
    its created_at. When a slug appears multiple times (status updates), the
    newest row wins for that slug so the ledger reads as current state."""
    rows = (
        await db.execute(
            select(StoryEvent.created_at, StoryEvent.actor, StoryEvent.signals)
            .where(StoryEvent.event_type == INCIDENT_EVENT)
            .order_by(StoryEvent.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
    ).all()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for created_at, actor, signals in rows:
        sig = dict(signals or {})
        slug = sig.get("slug") or ""
        if slug and slug in seen:
            continue  # older duplicate of an already-shown slug
        if slug:
            seen.add(slug)
        if not include_fixed and sig.get("status") == "fixed":
            continue
        out.append(
            {
                "created_at": created_at.isoformat() if created_at else None,
                "actor": actor,
                **sig,
            }
        )
    return out


async def human_intervention_rate(db: AsyncSession, *, days: int = 7) -> dict[str, Any]:
    """HIR — the North-Star self-running metric ([[project_self_running_kpis]]).

    Counts distinct defects FIRST surfaced by Parham (`detected_by='human'`) in
    the trailing window. A self-running product drives this to 0 — canaries and
    self-heals should be catching things instead of his eye. Also returns the
    detection-source breakdown so we can watch the canary-vs-human ratio climb.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = (
        await db.execute(
            select(StoryEvent.created_at, StoryEvent.signals)
            .where(StoryEvent.event_type == INCIDENT_EVENT)
            .order_by(StoryEvent.created_at.desc())
            .limit(500)
        )
    ).all()
    human_slugs: set[str] = set()
    by_source: dict[str, int] = {}
    for created_at, signals in rows:
        if created_at is None:
            continue
        ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        sig = dict(signals or {})
        src = sig.get("detected_by") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        if src == "human" and sig.get("slug"):
            human_slugs.add(sig["slug"])
    total = sum(by_source.values())
    auto = by_source.get("canary", 0) + by_source.get("self_heal", 0)
    return {
        "days": days,
        "hir": len(human_slugs),  # North-Star: target 0
        "human_slugs": sorted(human_slugs),
        "by_source": by_source,
        # share of incidents an automated signal caught first (target >= 0.9)
        "auto_detection_ratio": round(auto / total, 2) if total else None,
    }


async def self_review_packet(db: AsyncSession) -> dict[str, Any]:
    """One-read review packet: non-ok canaries + open incidents + recent
    maintenance fails. The chat ritual reads this, maps each signal to a
    responsible prompt/step, and proposes fixes + regression cases."""
    # Reuse the canary computation rather than duplicating it.
    from app.api.v1.admin import health_overview

    non_ok: list[dict[str, Any]] = []
    recent_fails: list[dict[str, Any]] = []
    try:
        hov = await health_overview(db)  # plain async fn; Depends not invoked
        for c in hov.get("canaries", []):
            if c.get("status") != "ok":
                non_ok.append(
                    {
                        "id": c.get("id"),
                        "status": c.get("status"),
                        "value": c.get("value"),
                        "why": (c.get("why") or "")[:300],
                    }
                )
        # last maintenance log's failing steps, if surfaced
        maint = hov.get("maintenance") or {}
        for f in (maint.get("recent_fails") or [])[:10]:
            recent_fails.append(f)
    except Exception as e:  # never let the packet itself error out
        non_ok.append({"id": "self_review_error", "status": "warn", "why": str(e)[:200]})

    open_incidents = [
        i for i in await list_incidents(db, limit=100)
        if i.get("status") in ("open", "monitoring")
    ]
    try:
        hir = await human_intervention_rate(db, days=7)
    except Exception as e:  # never let the packet error
        hir = {"error": str(e)[:200]}
    return {
        "hir_7d": hir,  # North-Star: distinct human-caught defects in 7d (target 0)
        "non_ok_canaries": non_ok,
        "open_incidents": open_incidents,
        "recent_maintenance_fails": recent_fails,
        "ritual": [
            "Map each non-ok canary + recent fail to the responsible prompt/step.",
            "log_incident() anything not already in open_incidents.",
            "Propose a versioned prompt/step edit + a golden case in test_regression_cases.py.",
            "Mark an incident 'fixed' (new row, same slug) once its regression case is green.",
        ],
        "counts": {
            "non_ok_canaries": len(non_ok),
            "open_incidents": len(open_incidents),
        },
    }


# Seed incidents — the real defects from the 2026-06-02/03 sessions. Idempotent
# by slug at the read layer (newest-per-slug wins), so re-running is harmless.
SEED_INCIDENTS = [
    {
        "slug": "pinned-umbrella-accretion",
        "title": "Pinned stories accrete forever and become grab-bags",
        "symptom": "82c03e04 (Hormuz hero) grew to 161→104 articles spanning the "
        "Khamenei assassination, Lebanon, negotiations, and a banana-theft story; "
        "oversized_active canary stuck red and never self-heals.",
        "root_cause": "A pinned/seeded story (is_edited) bypasses the 7-day "
        "freshness aging + freeze, so it keeps absorbing new articles indefinitely. "
        "The 30-cap canary also can't distinguish a coherent large war story from a grab-bag.",
        "responsible": "clustering pinned-umbrella accretion + oversized_active_stories canary",
        "fix": "2026-06-03 manual surgical re-audit (90 articles reorganized). "
        "GUARDRAIL TODO: pinned stories must respect a size cap + periodic coherence "
        "re-check, OR oversized canary exempts human-audited is_edited heroes / scales threshold in war.",
        "regression_case": None,
        "severity": "high",
        "status": "monitoring",
        "detected_by": "audit",
    },
    {
        "slug": "bellwether-demoted-coverage-false-positive",
        "title": "Bellwether flags covered-but-demoted stories as MISSING",
        "symptom": "First cron bellwether reported 'Iran attacks on US bases' MISSING "
        "(conf 0.9) though we covered it in two stories demoted to priority=-50.",
        "root_cause": "_our_top_titles fed the LLM only top-12-by-priority, so demoted "
        "coverage sorted out of view. Demoted != absent.",
        "responsible": "bellwether._our_top_titles",
        "fix": "Union the prominent slice with all fresh stories (any priority). Shipped 34e6376.",
        "regression_case": "test_case_2026_06_03_bellwether_compares_fresh_not_just_prominent",
        "severity": "med",
        "status": "fixed",
        "detected_by": "canary",
    },
    {
        "slug": "offtopic-label-produces-zero",
        "title": "off_topic content_type label produces 0 in production",
        "symptom": "Over 7 days, 0 articles labeled off_topic; off-domain junk lands "
        "in 'other' instead.",
        "root_cause": "The off-domain heuristic is high-precision and rarely fires; the "
        "LLM tends to pick 'other'. Protection still holds (both 'other' and 'off_topic' "
        "are dropped via allowed=['news']), so functionally fine — but the off_topic path is unexercised.",
        "responsible": "content_type heuristic + _LLM_PROMPT",
        "fix": "Monitor; consider broadening the off-domain heuristic only if real off-topic leaks onto the homepage.",
        "regression_case": "test_case_2026_06_02_sports_title_is_offtopic",
        "severity": "low",
        "status": "monitoring",
        "detected_by": "canary",
    },
]


async def seed_incidents(db: AsyncSession, *, commit: bool = True) -> int:
    """Write the seed incidents (idempotent at the read layer). Returns count."""
    existing = {i.get("slug") for i in await list_incidents(db, limit=200)}
    n = 0
    for inc in SEED_INCIDENTS:
        if inc["slug"] in existing:
            continue
        await log_incident(db, **inc, commit=False)
        n += 1
    if commit and n:
        await db.commit()
    return n


# Canaries worth turning into incidents — the content/quality signals that map
# to defects Parham would otherwise catch BY EYE. Ops/cost/translation canaries
# (rss_silent_7d, translation_*, budget, telegram fetch) are intentionally
# excluded: they're operational noise, not the homepage-quality defects the
# detection-source ratio is meant to track ([[project_self_running_kpis]] P4).
INCIDENT_WORTHY_CANARIES = {
    "midsize_grabbag_risk",
    "homepage_grabbag",
    "homepage_offtopic_leak",
    "bellwether_missing_story",
    "narrative_coverage_contradiction",
    "article_count_drift",
    "trending_freshness",
    "homepage_fresh_pool",
    "blindspot_fresh_pool",
    "oversized_active_stories",
    "breaking_news_unclustered",
}


async def sync_canary_incidents(db: AsyncSession) -> dict[str, Any]:
    """Auto-log a `detected_by='canary'` incident the moment a content-quality
    canary flips non-ok, and close it when it recovers. This is what lets the
    detection-source ratio move off 0.0: without it, canaries can fire forever
    and the scorecard still reads "every defect caught by a human".

    Transition-only + idempotent: ONE incident per firing episode, not one per
    cron. We check the latest ledger status per canary slug, so a persistent
    canary (e.g. trending_freshness during a long war) produces a single open
    incident, not a new row every 12h — and because `human_intervention_rate`
    counts rows in a trailing window, only genuine recent transitions move the
    ratio. Only canaries in INCIDENT_WORTHY_CANARIES are managed.
    """
    from app.api.v1.admin import health_overview  # local: avoid import cycle

    stats: dict[str, Any] = {"checked": 0, "opened": 0, "closed": 0}
    try:
        hov = await health_overview(db)
    except Exception as e:  # never fail the cron over monitoring
        return {**stats, "error": str(e)[:120]}

    existing = {i.get("slug"): i for i in await list_incidents(db, limit=300)}
    for c in (hov.get("canaries") or []):
        cid = c.get("id")
        if cid not in INCIDENT_WORTHY_CANARIES:
            continue
        stats["checked"] += 1
        status = c.get("status")
        slug = f"canary-{cid}"
        prev = existing.get(slug)
        prev_open = bool(prev) and prev.get("status") in ("open", "monitoring")
        if status in ("warn", "error"):
            if not prev_open:
                await log_incident(
                    db,
                    slug=slug,
                    title=f"Canary fired: {c.get('name') or cid}",
                    symptom=f"{c.get('name') or cid} = {c.get('value')}",
                    root_cause=(c.get("why") or "")[:600],
                    responsible=f"canary:{cid}",
                    severity="high" if status == "error" else "med",
                    status="open",
                    detected_by="canary",
                    actor="maintenance",
                    commit=False,
                )
                stats["opened"] += 1
        elif prev_open:  # canary back to ok — close the open incident
            await log_incident(
                db,
                slug=slug,
                title=f"Canary recovered: {c.get('name') or cid}",
                symptom=f"{c.get('name') or cid} back to ok ({c.get('value')})",
                root_cause=(prev.get("root_cause") or "canary recovered")[:600],
                responsible=f"canary:{cid}",
                severity="low",
                status="fixed",
                detected_by="canary",
                actor="maintenance",
                commit=False,
            )
            stats["closed"] += 1
    if stats["opened"] or stats["closed"]:
        await db.commit()
    return stats

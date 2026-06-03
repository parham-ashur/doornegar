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
    return {
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

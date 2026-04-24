"""Weekly worldview digests — public read.

  GET /worldviews/current
      → 4 most-recent cards, one per bundle (principlist, reformist,
        moderate_diaspora, radical_diaspora). Insufficient-signal weeks
        come through as status='insufficient' rows so the UI can render
        a labeled placeholder instead of hiding the bundle.

  GET /worldviews/{bundle}?window=YYYY-MM-DD
      → Single bundle detail. `window` is the Monday of the target ISO
        week (window_start). If omitted, the most recent available
        digest for that bundle is returned. Response includes the full
        evidence chain (belief → article_ids) so the UI can link each
        belief back to its source articles.

Editorial caveat (also surfaced by the frontend as a visible chip):
these cards describe what OUTLETS in the bundle told their readers,
not what readers or any demographic group believes.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.worldview_digest import WorldviewDigest
from app.services.narrative_groups import (
    NARRATIVE_GROUPS_ORDER,
    GROUP_LABELS_FA,
    NarrativeGroup,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────


class WorldviewCard(BaseModel):
    bundle: str
    bundle_label_fa: str
    window_start: date
    window_end: date
    status: str  # "ok" | "insufficient"
    article_count: int
    source_count: int
    coverage_pct: float
    synthesis_fa: dict | None = None
    # evidence_fa omitted from the /current list response to keep payload
    # small; the detail endpoint returns the full chain.
    model_used: str | None = None
    generated_at: datetime


class WorldviewDetail(WorldviewCard):
    evidence_fa: dict | None = None


class CurrentResponse(BaseModel):
    window_start: date | None
    window_end: date | None
    cards: list[WorldviewCard]


# ─── Helpers ─────────────────────────────────────────────────────────


def _to_card(row: WorldviewDigest, include_evidence: bool = False) -> dict:
    out = {
        "bundle": row.bundle,
        "bundle_label_fa": GROUP_LABELS_FA.get(row.bundle, row.bundle),
        "window_start": row.window_start,
        "window_end": row.window_end,
        "status": row.status,
        "article_count": row.article_count,
        "source_count": row.source_count,
        "coverage_pct": round(row.coverage_pct, 1),
        "synthesis_fa": row.synthesis_fa,
        "model_used": row.model_used,
        "generated_at": row.generated_at,
    }
    if include_evidence:
        out["evidence_fa"] = row.evidence_fa
    return out


async def _latest_per_bundle(
    db: AsyncSession,
) -> dict[NarrativeGroup, WorldviewDigest]:
    """Return the most-recent digest row per bundle (by window_start DESC)."""
    # Small table; fetch all rows and pick the freshest per bundle in python.
    res = await db.execute(
        select(WorldviewDigest).order_by(WorldviewDigest.window_start.desc())
    )
    latest: dict[NarrativeGroup, WorldviewDigest] = {}
    for row in res.scalars():
        if row.bundle not in latest:
            latest[row.bundle] = row
    return latest


# ─── Endpoints ───────────────────────────────────────────────────────


@router.get("/current", response_model=CurrentResponse)
async def get_current(db: AsyncSession = Depends(get_db)):
    """Return the 4 most-recent worldview cards.

    Cards are returned in the canonical 4-subgroup order (principlist,
    reformist, moderate_diaspora, radical_diaspora) so the frontend's
    2×2 layout can index positionally without resorting.
    """
    latest = await _latest_per_bundle(db)
    cards: list[dict] = []
    window_start: date | None = None
    window_end: date | None = None
    for bundle in NARRATIVE_GROUPS_ORDER:
        row = latest.get(bundle)
        if row is None:
            continue
        cards.append(_to_card(row, include_evidence=False))
        # Report the most recent window seen across bundles; bundles
        # should share windows but may briefly diverge if one bundle's
        # Monday run failed and was retried.
        if window_start is None or row.window_start > window_start:
            window_start = row.window_start
            window_end = row.window_end
    return {"window_start": window_start, "window_end": window_end, "cards": cards}


@router.get("/{bundle}", response_model=WorldviewDetail)
async def get_bundle_detail(
    bundle: str,
    window: date | None = Query(None, description="Monday of target week (window_start)"),
    db: AsyncSession = Depends(get_db),
):
    """Return a single bundle's worldview card with evidence chain."""
    if bundle not in NARRATIVE_GROUPS_ORDER:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown bundle: {bundle}. Expected one of {list(NARRATIVE_GROUPS_ORDER)}.",
        )

    stmt = select(WorldviewDigest).where(WorldviewDigest.bundle == bundle)
    if window is not None:
        stmt = stmt.where(WorldviewDigest.window_start == window)
    stmt = stmt.order_by(WorldviewDigest.window_start.desc()).limit(1)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No worldview digest found for that bundle/window yet.",
        )
    return _to_card(row, include_evidence=True)

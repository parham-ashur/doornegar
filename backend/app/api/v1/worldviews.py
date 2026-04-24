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

import asyncio
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import require_admin
from app.database import async_session, get_db
from app.models.article import Article
from app.models.source import Source
from app.models.worldview_digest import WorldviewDigest
from app.services.narrative_groups import (
    NARRATIVE_GROUPS_ORDER,
    GROUP_LABELS_FA,
    NarrativeGroup,
)
from app.services.worldview_digest import generate_worldview_digests

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


class EvidenceArticle(BaseModel):
    """One cited article, enriched with human-readable context.

    story_id lets the frontend link each chip to the containing story
    page (where the article actually lives), so readers aren't sent to
    /stories/{article_id} which 404s. `url` exposes the original outlet
    URL for readers who want to read the source directly.
    """
    id: str
    title_fa: str | None = None
    source_slug: str | None = None
    source_name_fa: str | None = None
    story_id: str | None = None
    url: str | None = None
    published_at: datetime | None = None


class WorldviewDetail(WorldviewCard):
    evidence_fa: dict | None = None
    # article_id → EvidenceArticle. Populated only on the detail
    # endpoint; the /current list endpoint returns only card-level data.
    evidence_articles: dict[str, EvidenceArticle] | None = None


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


def _collect_article_ids(synthesis: dict | None, evidence: dict | None) -> set[str]:
    """Pull every article UUID referenced anywhere in the card."""
    ids: set[str] = set()
    if isinstance(evidence, dict):
        for v in evidence.values():
            if isinstance(v, list):
                for a in v:
                    if isinstance(a, str) and a:
                        ids.add(a)
    if isinstance(synthesis, dict):
        for key in ("core_beliefs", "emphasized", "predictions_primed"):
            for entry in synthesis.get(key) or []:
                if not isinstance(entry, dict):
                    continue
                for a in entry.get("example_article_ids") or []:
                    if isinstance(a, str) and a:
                        ids.add(a)
    return ids


async def _load_evidence_articles(
    db: AsyncSession, article_ids: set[str]
) -> dict[str, dict]:
    """One query → {article_id: {title, source, story_id, url, ...}}."""
    if not article_ids:
        return {}
    res = await db.execute(
        select(Article, Source)
        .join(Source, Article.source_id == Source.id, isouter=True)
        .where(Article.id.in_(article_ids))
    )
    out: dict[str, dict] = {}
    for article, source in res.all():
        out[str(article.id)] = {
            "id": str(article.id),
            "title_fa": article.title_fa or article.title_original or article.title_en,
            "source_slug": source.slug if source else None,
            "source_name_fa": source.name_fa if source else None,
            "story_id": str(article.story_id) if article.story_id else None,
            "url": article.url,
            "published_at": article.published_at,
        }
    return out


@router.get("/{bundle}", response_model=WorldviewDetail)
async def get_bundle_detail(
    bundle: str,
    window: date | None = Query(None, description="Monday of target week (window_start)"),
    db: AsyncSession = Depends(get_db),
):
    """Return a single bundle's worldview card with evidence chain.

    Also enriches every cited article_id with its title, source, URL, and
    containing story_id so the frontend can render meaningful links
    instead of raw UUID chips that 404 into /stories/{article_id}.
    """
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
    card = _to_card(row, include_evidence=True)
    article_ids = _collect_article_ids(row.synthesis_fa, row.evidence_fa)
    card["evidence_articles"] = await _load_evidence_articles(db, article_ids)
    return card


# ─── Admin trigger (on-demand run) ───────────────────────────────────


async def _run_synthesis_detached(anchor: date | None) -> None:
    """Run the weekly synthesis in its own DB session, detached from the
    originating request. Called via asyncio.create_task() below so the
    HTTP response can return immediately — synthesis takes ~30-90s
    across 4 bundles and otherwise trips Cloudflare's 100s edge timeout.
    """
    try:
        async with async_session() as db:
            stats = await generate_worldview_digests(db, anchor=anchor)
            logger.info(
                "admin/generate complete: bundles=%s total_cost=$%s",
                {k: v.get("status") for k, v in stats.get("per_bundle", {}).items()},
                stats.get("total_cost_usd", 0),
            )
    except Exception:
        logger.exception("worldview_digest background synthesis failed")


@router.post(
    "/admin/generate",
    dependencies=[Depends(require_admin)],
    status_code=202,
    summary="Kick off worldview synthesis in the background (returns 202).",
)
async def admin_generate(
    anchor: date | None = Query(
        None,
        description=(
            "Optional anchor date. Window is the ISO week ending on "
            "anchor's Monday (i.e. the previous full week). If omitted, "
            "uses today's week anchor."
        ),
    ),
):
    """Fire-and-forget synthesis trigger.

    Returns 202 Accepted immediately; the actual work runs in a detached
    asyncio task so long synthesis runs (4 bundles × OpenAI calls) don't
    hit Cloudflare's 100s edge timeout. Poll GET /worldviews/current to
    see when the new rows land — `generated_at` advances on each bundle.

    Same preconditions + same cost logging as the scheduled Monday run.
    """
    asyncio.create_task(_run_synthesis_detached(anchor))
    return {
        "status": "accepted",
        "message": "Synthesis running in background. Poll /api/v1/worldviews/current to see results.",
        "anchor": anchor.isoformat() if anchor else None,
    }

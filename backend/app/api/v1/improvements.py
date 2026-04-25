"""Improvement feedback API — rater submissions + admin todo list."""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import require_admin
from app.database import get_db
from app.models.improvement import ImprovementFeedback
from app.rate_limit import limiter as _limiter
from app.schemas.improvement import (
    ImprovementDetail,
    ImprovementListResponse,
    ImprovementResponse,
    ImprovementSubmit,
    ImprovementUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Rater submission ─────────────────────────────────────────
# Public for now, rate-limited. Can add auth later when rater accounts
# are in use.

@router.post("", response_model=ImprovementResponse)
@_limiter.limit("60/hour")
async def submit_feedback(
    request: Request,
    body: ImprovementSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit improvement feedback. Rate-limited to 60/hour/IP."""
    # Count similar open/in_progress items flagged by others with the same
    # target and issue type. Used for the "X others flagged this" hint.
    similar_count = 0
    if body.target_id:
        result = await db.execute(
            select(func.count(ImprovementFeedback.id)).where(
                and_(
                    ImprovementFeedback.target_type == body.target_type,
                    ImprovementFeedback.target_id == body.target_id,
                    ImprovementFeedback.issue_type == body.issue_type,
                    ImprovementFeedback.status.in_(["open", "in_progress"]),
                )
            )
        )
        similar_count = result.scalar() or 0

    # Soft fingerprint of the submitter — IP + UA + accept-language hashed
    # together. Lets step_rater_feedback_apply count *distinct* anonymous
    # voters per article instead of raw row count, so one person can't
    # vote 3 times to trip auto-orphan. Not strong identity (VPN/private
    # browsing dodges) — just a brigading deterrent at the small-audience
    # scale Doornegar is at.
    client_host = request.client.host if request.client else ""
    fp_input = (
        f"{client_host}|"
        f"{request.headers.get('user-agent', '')[:200]}|"
        f"{request.headers.get('accept-language', '')[:32]}"
    )
    fingerprint = hashlib.sha256(fp_input.encode("utf-8", "replace")).hexdigest()[:40]

    item = ImprovementFeedback(
        target_type=body.target_type,
        target_id=body.target_id,
        target_url=body.target_url,
        issue_type=body.issue_type,
        current_value=body.current_value,
        suggested_value=body.suggested_value,
        reason=body.reason,
        rater_name=body.rater_name,
        rater_contact=body.rater_contact,
        priority=body.priority,
        device_info=body.device_info,
        submitter_fingerprint=fingerprint,
        status="open",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    logger.info(f"New improvement feedback: {body.target_type} / {body.issue_type}")

    return ImprovementResponse(
        id=item.id,
        status="open",
        message="متشکریم. پیشنهاد شما ثبت شد.",
        similar_count=similar_count,
    )


# ─── Self-service retraction (Undo within 60 seconds) ────────

@router.delete("/self/{item_id}", status_code=200)
@_limiter.limit("30/hour")
async def retract_feedback(
    request: Request,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Allow a rater to delete their own feedback within 60 seconds of creation.

    This is a self-service undo. No auth required, but the item must have
    been created within the last 60 seconds and must still be in 'open' status.
    """
    result = await db.execute(
        select(ImprovementFeedback).where(ImprovementFeedback.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    age = datetime.now(timezone.utc) - item.created_at
    if age > timedelta(seconds=60):
        raise HTTPException(status_code=403, detail="Too late to undo")
    if item.status != "open":
        raise HTTPException(status_code=403, detail="Already being processed")

    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}


# ─── Admin endpoints ──────────────────────────────────────────

@router.get(
    "/admin",
    response_model=ImprovementListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_feedback(
    status: str | None = Query(None),
    issue_type: str | None = Query(None),
    target_type: str | None = Query(None),
    include_bot: bool = Query(False, description="Include entries from the maintenance bot (default: hide)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Admin todo list with filters.

    By default, hides entries where `device_info='maintenance-bot'` —
    the maintenance pipeline auto-detaches low-similarity articles
    rather than queueing them for human review, so this list should
    show only rater-submitted issues. Pass include_bot=true to see
    any residual bot entries (useful during migration).
    """
    base_filter = []
    if not include_bot:
        # Treat NULL device_info as non-bot (raters don't always send it)
        base_filter.append(
            (ImprovementFeedback.device_info != "maintenance-bot")
            | (ImprovementFeedback.device_info.is_(None))
        )
    if status:
        base_filter.append(ImprovementFeedback.status == status)
    if issue_type:
        base_filter.append(ImprovementFeedback.issue_type == issue_type)
    if target_type:
        base_filter.append(ImprovementFeedback.target_type == target_type)

    query = select(ImprovementFeedback).order_by(ImprovementFeedback.created_at.desc())
    for f in base_filter:
        query = query.where(f)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    # Totals also exclude bot entries so the header counters match the visible list.
    def _count(extra_filter=None):
        q = select(func.count(ImprovementFeedback.id))
        if not include_bot:
            q = q.where(
                (ImprovementFeedback.device_info != "maintenance-bot")
                | (ImprovementFeedback.device_info.is_(None))
            )
        if extra_filter is not None:
            q = q.where(extra_filter)
        return q

    total = (await db.execute(_count())).scalar() or 0
    open_count = (await db.execute(_count(ImprovementFeedback.status == "open"))).scalar() or 0
    in_progress = (await db.execute(_count(ImprovementFeedback.status == "in_progress"))).scalar() or 0

    return ImprovementListResponse(
        items=[ImprovementDetail.model_validate(i) for i in items],
        total=total,
        open=open_count,
        in_progress=in_progress,
    )


@router.patch(
    "/admin/{item_id}",
    response_model=ImprovementDetail,
    dependencies=[Depends(require_admin)],
)
async def update_feedback(
    item_id: uuid.UUID,
    body: ImprovementUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ImprovementFeedback).where(ImprovementFeedback.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if body.status is not None:
        item.status = body.status
        if body.status in ("done", "wont_do", "duplicate"):
            item.resolved_at = datetime.now(timezone.utc)
    if body.priority is not None:
        item.priority = body.priority
    if body.admin_notes is not None:
        item.admin_notes = body.admin_notes

    await db.commit()
    await db.refresh(item)
    return ImprovementDetail.model_validate(item)


@router.delete(
    "/admin/{item_id}",
    dependencies=[Depends(require_admin)],
)
async def delete_feedback(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ImprovementFeedback).where(ImprovementFeedback.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}

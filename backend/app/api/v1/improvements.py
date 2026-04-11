"""Improvement feedback API — rater submissions + admin todo list."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
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
    """Submit improvement feedback. Rate-limited to 30/hour/IP."""
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
    )


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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Admin todo list with filters."""
    query = select(ImprovementFeedback).order_by(ImprovementFeedback.created_at.desc())

    if status:
        query = query.where(ImprovementFeedback.status == status)
    if issue_type:
        query = query.where(ImprovementFeedback.issue_type == issue_type)
    if target_type:
        query = query.where(ImprovementFeedback.target_type == target_type)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    total = (await db.execute(select(func.count(ImprovementFeedback.id)))).scalar() or 0
    open_count = (
        await db.execute(
            select(func.count(ImprovementFeedback.id)).where(
                ImprovementFeedback.status == "open"
            )
        )
    ).scalar() or 0
    in_progress = (
        await db.execute(
            select(func.count(ImprovementFeedback.id)).where(
                ImprovementFeedback.status == "in_progress"
            )
        )
    ).scalar() or 0

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

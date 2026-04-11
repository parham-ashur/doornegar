"""Source suggestions API — public submission + admin review."""

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import require_admin
from app.database import get_db
from app.models.suggestion import SourceSuggestion
from app.rate_limit import limiter as _limiter
from app.schemas.suggestion import (
    SuggestionDetail,
    SuggestionListResponse,
    SuggestionResponse,
    SuggestionSubmit,
    SuggestionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _ip_hash(request: Request) -> str:
    """Salted hash of client IP for rate-limit tracking only.

    We intentionally don't store raw IPs. This hash is used to spot abuse
    patterns (many submissions from one IP) without keeping personal data.
    """
    ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    # Rotating salt would be better — for now, a static salt is fine since
    # the hash is not persisted beyond a short lifecycle
    salted = f"iid-suggestion-salt:{ip}"
    return hashlib.sha256(salted.encode()).hexdigest()


# ─── Public submission ────────────────────────────────────────

@router.post("", response_model=SuggestionResponse)
@_limiter.limit("5/hour")
async def submit_suggestion(
    request: Request,
    body: SuggestionSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit a source suggestion. Public endpoint, rate-limited to 5/hour/IP."""
    # Basic spam filter: same URL already suggested recently?
    existing = await db.execute(
        select(SourceSuggestion).where(SourceSuggestion.url == body.url)
    )
    duplicate = existing.scalar_one_or_none()
    if duplicate:
        return SuggestionResponse(
            id=duplicate.id,
            status="duplicate",
            message="این منبع قبلاً پیشنهاد شده است. متشکریم.",
        )

    suggestion = SourceSuggestion(
        suggestion_type=body.suggestion_type,
        name=body.name.strip(),
        url=body.url.strip(),
        language=body.language,
        suggested_category=body.suggested_category,
        description=body.description,
        submitter_name=body.submitter_name,
        submitter_contact=body.submitter_contact,
        submitter_notes=body.submitter_notes,
        status="pending",
        ip_hash=_ip_hash(request),
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)

    logger.info(f"New suggestion: {body.suggestion_type} / {body.name}")

    return SuggestionResponse(
        id=suggestion.id,
        status="pending",
        message="متشکریم. پیشنهاد شما دریافت شد و بررسی خواهد شد.",
    )


# ─── Admin endpoints ──────────────────────────────────────────

@router.get(
    "/admin",
    response_model=SuggestionListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_suggestions(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List suggestions (admin only). Filter by status."""
    query = select(SourceSuggestion).order_by(SourceSuggestion.created_at.desc())

    if status:
        query = query.where(SourceSuggestion.status == status)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    suggestions = list(result.scalars().all())

    # Totals
    total = (await db.execute(select(func.count(SourceSuggestion.id)))).scalar() or 0
    pending = (
        await db.execute(
            select(func.count(SourceSuggestion.id)).where(
                SourceSuggestion.status == "pending"
            )
        )
    ).scalar() or 0

    return SuggestionListResponse(
        suggestions=[SuggestionDetail.model_validate(s) for s in suggestions],
        total=total,
        pending=pending,
    )


@router.patch(
    "/admin/{suggestion_id}",
    response_model=SuggestionDetail,
    dependencies=[Depends(require_admin)],
)
async def update_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a suggestion's status or reviewer notes (admin only)."""
    result = await db.execute(
        select(SourceSuggestion).where(SourceSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if body.status is not None:
        suggestion.status = body.status
        if body.status != "pending":
            suggestion.reviewed_at = datetime.now(timezone.utc)
    if body.reviewer_notes is not None:
        suggestion.reviewer_notes = body.reviewer_notes

    await db.commit()
    await db.refresh(suggestion)
    return SuggestionDetail.model_validate(suggestion)


@router.delete(
    "/admin/{suggestion_id}",
    dependencies=[Depends(require_admin)],
)
async def delete_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a suggestion (admin only)."""
    result = await db.execute(
        select(SourceSuggestion).where(SourceSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    await db.delete(suggestion)
    await db.commit()
    return {"status": "deleted"}

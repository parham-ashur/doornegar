"""Public content-submission endpoint + admin review list.

Readers paste an article, Telegram post, Instagram excerpt, or other raw
source material via the /[locale]/submit form. Each submission can
optionally link to an existing story. Niloofar reviews the pending
queue and either accepts (attaches to the right cluster), rejects
(spam / off-topic), or marks as a duplicate of something already
ingested.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import require_admin
from app.database import get_db
from app.models.user_submission import UserSubmission
from app.rate_limit import limiter as _limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────


class SubmissionCreate(BaseModel):
    submission_type: Literal[
        "article", "telegram_post", "instagram_post", "news", "other"
    ]
    suggested_story_id: str | None = None
    title: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=10, max_length=20000)
    source_name: str | None = Field(default=None, max_length=255)
    source_url: str | None = None
    channel_username: str | None = Field(default=None, max_length=100)
    is_analyst: bool | None = None
    language: Literal["fa", "en"] = "fa"
    submitter_name: str | None = Field(default=None, max_length=100)
    submitter_contact: str | None = Field(default=None, max_length=200)
    submitter_note: str | None = Field(default=None, max_length=2000)


class SubmissionResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str


class SubmissionItem(BaseModel):
    id: uuid.UUID
    submission_type: str
    suggested_story_id: str | None
    title: str | None
    content: str
    source_name: str | None
    source_url: str | None
    channel_username: str | None
    is_analyst: bool | None
    language: str
    submitter_name: str | None
    submitter_contact: str | None
    submitter_note: str | None
    status: str
    admin_notes: str | None
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class SubmissionListResponse(BaseModel):
    items: list[SubmissionItem]
    total: int


class SubmissionUpdate(BaseModel):
    status: Literal[
        "pending", "accepted_article", "accepted_post", "rejected", "duplicate"
    ]
    admin_notes: str | None = None


# ─── Public POST ─────────────────────────────────────────────


@router.post("", response_model=SubmissionResponse)
@_limiter.limit("10/hour")
async def create_submission(
    request: Request,
    body: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Accept a content submission from the public. Rate-limited to
    10/hour/IP to deter spam. Returns the created submission's ID so
    the frontend can show "your submission #XYZ is pending review".
    """
    # Light validation for telegram-post shape
    if body.submission_type == "telegram_post" and not body.channel_username:
        raise HTTPException(
            status_code=400,
            detail="telegram_post submissions must include channel_username",
        )

    ip = request.client.host if request.client else None

    item = UserSubmission(
        submission_type=body.submission_type,
        suggested_story_id=body.suggested_story_id,
        title=body.title,
        content=body.content,
        source_name=body.source_name,
        source_url=body.source_url,
        channel_username=(body.channel_username or "").lstrip("@") or None,
        is_analyst=body.is_analyst,
        language=body.language,
        submitter_name=body.submitter_name,
        submitter_contact=body.submitter_contact,
        submitter_note=body.submitter_note,
        submitter_ip=ip,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    logger.info(
        f"New submission {item.id} type={item.submission_type} "
        f"linked_to={item.suggested_story_id or '-'}"
    )
    return SubmissionResponse(
        id=item.id,
        status="pending",
        message="متشکریم — ارسال شما در صف بررسی قرار گرفت.",
    )


# ─── Admin list / update ─────────────────────────────────────


@router.get(
    "",
    response_model=SubmissionListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_submissions(
    status: str | None = Query(
        default=None,
        description="Filter: pending | accepted_article | accepted_post | rejected | duplicate",
    ),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(UserSubmission).order_by(desc(UserSubmission.created_at)).limit(limit)
    if status:
        stmt = stmt.where(UserSubmission.status == status)
    result = await db.execute(stmt)
    items = [SubmissionItem.model_validate(i) for i in result.scalars().all()]
    return SubmissionListResponse(items=items, total=len(items))


@router.patch(
    "/{submission_id}",
    response_model=SubmissionItem,
    dependencies=[Depends(require_admin)],
)
async def update_submission(
    submission_id: uuid.UUID,
    body: SubmissionUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(UserSubmission, submission_id)
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")
    item.status = body.status
    if body.admin_notes is not None:
        item.admin_notes = body.admin_notes
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return SubmissionItem.model_validate(item)

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
    image_url: str | None = None
    published_at: str | None = None  # ISO-8601
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
    image_url: str | None
    published_at: datetime | None
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


def _normalize_for_hash(text: str) -> str:
    """Collapse whitespace + strip zero-width chars before hashing so
    "same content with extra spaces" counts as a duplicate."""
    import re
    # Strip common zero-width and bidi markers that Persian text often carries
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    # Collapse all whitespace runs to a single space
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


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

    Dedup layers (cheap-first):
      1. source_url exact match against existing Articles → already in system
      2. source_url exact match against prior UserSubmissions → pending dup
      3. SHA-256 of normalized content matches prior UserSubmission → text dup
    Any hit short-circuits to a 200 response with a friendly message so
    the submitter sees "already in the system" instead of silently
    queuing a duplicate.
    """
    import hashlib

    from app.models.article import Article

    # Light validation for telegram-post shape
    if body.submission_type == "telegram_post" and not body.channel_username:
        raise HTTPException(
            status_code=400,
            detail="telegram_post submissions must include channel_username",
        )

    # ── Dedup checks ──
    if body.source_url:
        existing_art = (
            await db.execute(select(Article).where(Article.url == body.source_url))
        ).scalar_one_or_none()
        if existing_art:
            return SubmissionResponse(
                id=uuid.uuid4(),
                status="duplicate",
                message="این مقاله قبلاً در دورنگر ثبت شده است (با همین لینک).",
            )
        existing_sub = (
            await db.execute(
                select(UserSubmission).where(UserSubmission.source_url == body.source_url)
            )
        ).scalar_one_or_none()
        if existing_sub:
            return SubmissionResponse(
                id=existing_sub.id,
                status="duplicate",
                message=f"این لینک قبلاً ارسال شده و در وضعیت «{existing_sub.status}» است.",
            )

    content_hash = hashlib.sha256(
        _normalize_for_hash(body.content).encode("utf-8")
    ).hexdigest()
    existing_hash = (
        await db.execute(
            select(UserSubmission).where(UserSubmission.content_hash == content_hash)
        )
    ).scalar_one_or_none()
    if existing_hash:
        return SubmissionResponse(
            id=existing_hash.id,
            status="duplicate",
            message=f"متن یکسانی قبلاً ارسال شده (وضعیت: «{existing_hash.status}»).",
        )

    ip = request.client.host if request.client else None

    # Parse optional published_at (accept HTML datetime-local "YYYY-MM-DDTHH:MM"
    # as well as ISO-8601 with timezone)
    parsed_published = None
    if body.published_at:
        try:
            from datetime import datetime as _dt
            parsed_published = _dt.fromisoformat(body.published_at.replace("Z", "+00:00"))
        except Exception:
            parsed_published = None  # silent drop — not worth rejecting the whole submission

    item = UserSubmission(
        submission_type=body.submission_type,
        suggested_story_id=body.suggested_story_id,
        title=body.title,
        content=body.content,
        content_hash=content_hash,
        source_name=body.source_name,
        source_url=body.source_url,
        channel_username=(body.channel_username or "").lstrip("@") or None,
        is_analyst=body.is_analyst,
        language=body.language,
        image_url=body.image_url,
        published_at=parsed_published,
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
    """Review a submission.

    What happens on each status:
      - `accepted_article`: creates an Article row (or updates existing
        if URL matches) and attaches it to `suggested_story_id` when set.
        If no story_id, the article enters the unlinked pool and the
        next clustering step picks it up.
      - `accepted_post`: creates a TelegramChannel if channel_username
        is new, then inserts a TelegramPost linked to `suggested_story_id`.
        Invalidates that story's cached telegram_analysis so the next
        homepage render regenerates with the new post included.
      - `rejected` / `duplicate` / `pending`: status-only change.

    The original submission row stays in place for audit — status, admin
    notes, and reviewed_at are stamped but the content isn't deleted.
    """
    item = await db.get(UserSubmission, submission_id)
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")

    now = datetime.now(timezone.utc)

    if body.status == "accepted_article":
        from app.models.source import Source
        from app.models.article import Article
        from sqlalchemy.dialects.postgresql import insert as _pg_insert
        from sqlalchemy import select as _sel

        # Find or create a synthetic "user-submitted" source so the article
        # has a valid source_id FK. One row per locale is plenty.
        slug = f"user-submitted-{item.language}"
        src = (await db.execute(_sel(Source).where(Source.slug == slug))).scalar_one_or_none()
        if not src:
            src = Source(
                name_en="User submitted" if item.language == "en" else "ارسال‌های کاربران",
                name_fa="ارسال‌های کاربران",
                slug=slug,
                website_url="https://doornegar.org/submit",
                state_alignment="independent",
                production_location="outside_iran",
                language=item.language,
                is_active=True,
            )
            db.add(src)
            await db.flush()

        # Use the submitter's real source_url when they provided one — lets
        # on_conflict_do_nothing catch an article that's since been ingested
        # by the regular RSS pipeline. Fall back to a synthetic URL so the
        # FK still has a unique value when no link was provided.
        article_url = item.source_url or f"https://doornegar.org/submissions/{item.id}"
        stmt = (
            _pg_insert(Article)
            .values(
                source_id=src.id,
                title_original=item.title or (item.content[:80] + "…"),
                title_fa=item.title if item.language == "fa" else None,
                title_en=item.title if item.language == "en" else None,
                url=article_url,
                content_text=item.content,
                image_url=item.image_url,
                language=item.language,
                published_at=item.published_at or now,
                story_id=uuid.UUID(item.suggested_story_id) if item.suggested_story_id else None,
            )
            .on_conflict_do_nothing(index_elements=["url"])
        )
        await db.execute(stmt)

    elif body.status == "accepted_post":
        from sqlalchemy import select as _sel

        if not item.channel_username:
            raise HTTPException(status_code=400, detail="channel_username required to accept as post")

        from app.models.social import TelegramChannel, TelegramPost

        ch = (
            await db.execute(_sel(TelegramChannel).where(TelegramChannel.username == item.channel_username))
        ).scalar_one_or_none()
        if not ch:
            ch = TelegramChannel(
                username=item.channel_username,
                title=item.source_name or item.channel_username,
                channel_type="commentary" if item.is_analyst else "news",
                is_active=True,
            )
            db.add(ch)
            await db.flush()

        tp = TelegramPost(
            channel_id=ch.id,
            text=item.content,
            date=item.published_at or now,
            story_id=uuid.UUID(item.suggested_story_id) if item.suggested_story_id else None,
        )
        db.add(tp)
        # Invalidate the linked story's analysis so next read regenerates
        if item.suggested_story_id:
            from app.models.story import Story as _Story
            from sqlalchemy import update as _upd

            await db.execute(
                _upd(_Story)
                .where(_Story.id == uuid.UUID(item.suggested_story_id))
                .values(telegram_analysis=None)
            )

    item.status = body.status
    if body.admin_notes is not None:
        item.admin_notes = body.admin_notes
    item.reviewed_at = now
    await db.commit()
    await db.refresh(item)
    return SubmissionItem.model_validate(item)

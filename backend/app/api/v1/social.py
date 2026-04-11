"""API endpoints for social media (Telegram) data."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.social import SocialSentimentSnapshot, TelegramChannel, TelegramPost
from app.schemas.social import (
    SocialSentimentResponse,
    StoryPostsResponse,
    TelegramChannelCreate,
    TelegramChannelResponse,
    TelegramPostResponse,
)

router = APIRouter()


@router.get("/channels", response_model=list[TelegramChannelResponse])
async def list_channels(
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """List all tracked Telegram channels."""
    result = await db.execute(
        select(TelegramChannel)
        .where(TelegramChannel.is_active == is_active)
        .order_by(TelegramChannel.username)
    )
    channels = result.scalars().all()
    return [TelegramChannelResponse.model_validate(c) for c in channels]


@router.post("/channels", response_model=TelegramChannelResponse)
async def add_channel(
    channel: TelegramChannelCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new Telegram channel to track."""
    # Check for duplicate
    existing = await db.execute(
        select(TelegramChannel).where(TelegramChannel.username == channel.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Channel already tracked")

    new_channel = TelegramChannel(**channel.model_dump())
    db.add(new_channel)
    await db.commit()
    await db.refresh(new_channel)
    return TelegramChannelResponse.model_validate(new_channel)


@router.get("/stories/{story_id}/social", response_model=StoryPostsResponse)
async def get_story_social_data(
    story_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get Telegram posts and sentiment data linked to a story.

    Posts from channels mapped to Source records (via CHANNEL_SOURCE_MAP) are
    excluded — those posts are already shown as articles in the main article
    list. Only true "social reaction" posts from unmapped channels are returned.
    """
    from app.services.telegram_service import CHANNEL_SOURCE_MAP

    mapped_usernames = set(CHANNEL_SOURCE_MAP.keys())

    # Get posts, excluding those from mapped channels (to avoid duplication)
    query = (
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .join(TelegramPost.channel)
        .where(TelegramPost.story_id == story_id)
        .order_by(TelegramPost.date.desc())
        .limit(limit)
    )
    if mapped_usernames:
        from app.models.social import TelegramChannel
        query = query.where(~TelegramChannel.username.in_(mapped_usernames))

    result = await db.execute(query)
    posts = result.scalars().all()

    # Get total count (also excluding mapped channels)
    from app.models.social import TelegramChannel as _TC
    count_query = (
        select(func.count(TelegramPost.id))
        .join(TelegramPost.channel)
        .where(TelegramPost.story_id == story_id)
    )
    if mapped_usernames:
        count_query = count_query.where(~_TC.username.in_(mapped_usernames))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get latest sentiment snapshot
    sentiment_result = await db.execute(
        select(SocialSentimentSnapshot)
        .where(SocialSentimentSnapshot.story_id == story_id)
        .order_by(SocialSentimentSnapshot.snapshot_at.desc())
        .limit(1)
    )
    sentiment = sentiment_result.scalar_one_or_none()

    return StoryPostsResponse(
        story_id=story_id,
        posts=[TelegramPostResponse.model_validate(p) for p in posts],
        sentiment=SocialSentimentResponse.model_validate(sentiment) if sentiment else None,
        total_posts=total,
    )


@router.get("/stories/{story_id}/sentiment/history", response_model=list[SocialSentimentResponse])
async def get_sentiment_history(
    story_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get sentiment snapshots over time for a story — shows how opinion evolves."""
    result = await db.execute(
        select(SocialSentimentSnapshot)
        .where(SocialSentimentSnapshot.story_id == story_id)
        .order_by(SocialSentimentSnapshot.snapshot_at.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()
    return [SocialSentimentResponse.model_validate(s) for s in snapshots]

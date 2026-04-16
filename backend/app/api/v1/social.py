"""API endpoints for social media (Telegram) data."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.admin import require_admin
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


@router.post("/channels", response_model=TelegramChannelResponse, dependencies=[Depends(require_admin)])
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


@router.get("/recent", response_model=list[TelegramPostResponse])
async def get_recent_posts(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get most recent Telegram posts across all active channels (for homepage)."""
    result = await db.execute(
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .join(TelegramPost.channel)
        .where(TelegramChannel.is_active == True)  # noqa: E712
        .where(TelegramPost.text.isnot(None))
        .where(TelegramPost.text != "")
        .order_by(TelegramPost.date.desc())
        .limit(limit)
    )
    posts = result.scalars().all()
    return [TelegramPostResponse.model_validate(p) for p in posts]


@router.get("/stories/{story_id}/telegram-analysis")
async def get_telegram_analysis(
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Deep LLM analysis of Telegram discourse around a story.

    Returns cached analysis if available, otherwise runs LLM analysis and caches it.
    """
    from app.models.story import Story

    # Channel stats — only non-media channels (analysts, commentators, aggregators)
    NON_MEDIA_TYPES = ("commentary", "aggregator", "activist", "political_party", "citizen")
    channel_stats = []
    posts_result = await db.execute(
        select(TelegramChannel.title, TelegramChannel.channel_type, func.count(TelegramPost.id).label("cnt"))
        .join(TelegramPost, TelegramPost.channel_id == TelegramChannel.id)
        .where(TelegramPost.story_id == story_id)
        .where(TelegramPost.text.isnot(None))
        .where(TelegramChannel.channel_type.in_(NON_MEDIA_TYPES))
        .group_by(TelegramChannel.id, TelegramChannel.title, TelegramChannel.channel_type)
        .order_by(func.count(TelegramPost.id).desc())
    )
    for title, ch_type, cnt in posts_result.all():
        channel_stats.append({"name": title, "type": ch_type, "posts": cnt})
    total_posts = sum(c["posts"] for c in channel_stats)

    # Check for cached analysis first
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if story and story.telegram_analysis:
        return {"status": "ok", "analysis": story.telegram_analysis, "channels": channel_stats, "total_posts": total_posts}

    # No cache — run analysis and store
    from app.services.telegram_analysis import analyze_story_telegram
    result = await analyze_story_telegram(db, str(story_id))
    if result is None:
        return {"status": "no_data", "message": "Not enough Telegram posts for analysis", "channels": channel_stats, "total_posts": total_posts}

    # Cache in DB
    if story:
        story.telegram_analysis = result
        await db.commit()

    return {"status": "ok", "analysis": result, "channels": channel_stats, "total_posts": total_posts}


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

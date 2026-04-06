"""Rating endpoints for invited raters.

Raters see articles blind (no source attribution) and rate them
on 5 dimensions. Only authenticated raters can submit ratings.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.article import Article
from app.models.rating import CommunityRating
from app.models.user import User
from app.schemas.rating import RatingCreate, RatingResponse
from app.services.auth import get_current_user

router = APIRouter()


async def require_rater(
    authorization: str = Header(""),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: require authenticated rater."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not user.is_rater or not user.is_active:
        raise HTTPException(status_code=403, detail="Not authorized to rate")
    return user


@router.get("/next")
async def get_next_article_to_rate(
    user: User = Depends(require_rater),
    db: AsyncSession = Depends(get_db),
):
    """Get the next article for this rater to rate (blind — no source info).

    Returns an article that:
    1. Is part of a story (has been clustered)
    2. Has not been rated by this user yet
    """
    # Find articles this user hasn't rated yet
    rated_ids = select(CommunityRating.article_id).where(
        CommunityRating.user_id == user.id
    )

    result = await db.execute(
        select(Article)
        .where(
            Article.story_id.isnot(None),
            Article.id.notin_(rated_ids),
        )
        .order_by(func.random())
        .limit(1)
    )
    article = result.scalar_one_or_none()

    if not article:
        return {"status": "no_articles", "message": "No more articles to rate"}

    # Return article WITHOUT source info (blind rating)
    return {
        "status": "ok",
        "article": {
            "id": str(article.id),
            "title": article.title_original,
            "summary": article.summary,
            "content_text": article.content_text,
            "language": article.language,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            # Source is intentionally HIDDEN for blind rating
        },
    }


@router.post("/{article_id}")
async def submit_rating(
    article_id: uuid.UUID,
    rating: RatingCreate,
    user: User = Depends(require_rater),
    db: AsyncSession = Depends(get_db),
):
    """Submit a rating for an article."""
    # Check article exists
    article = await db.execute(select(Article).where(Article.id == article_id))
    if not article.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Article not found")

    # Check not already rated
    existing = await db.execute(
        select(CommunityRating).where(
            CommunityRating.user_id == user.id,
            CommunityRating.article_id == article_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already rated this article")

    # Create rating
    new_rating = CommunityRating(
        user_id=user.id,
        article_id=article_id,
        political_alignment_rating=rating.political_alignment_rating,
        factuality_rating=rating.factuality_rating,
        framing_labels=rating.framing_labels,
        tone_rating=rating.tone_rating,
        emotional_language_rating=rating.emotional_language_rating,
        notes=rating.notes,
        was_blind=rating.was_blind,
        time_spent_seconds=rating.time_spent_seconds,
    )
    db.add(new_rating)

    # Update user stats
    user.total_ratings += 1
    await db.commit()

    return {"status": "ok", "rating_id": str(new_rating.id), "total_ratings": user.total_ratings}


@router.get("/history")
async def get_rating_history(
    user: User = Depends(require_rater),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get this rater's rating history."""
    result = await db.execute(
        select(CommunityRating)
        .where(CommunityRating.user_id == user.id)
        .order_by(CommunityRating.created_at.desc())
        .limit(limit)
    )
    ratings = result.scalars().all()

    return {
        "ratings": [RatingResponse.model_validate(r) for r in ratings],
        "total": user.total_ratings,
    }


@router.get("/stats")
async def get_rating_stats(db: AsyncSession = Depends(get_db)):
    """Public endpoint: aggregate rating statistics."""
    total_ratings = (await db.execute(select(func.count(CommunityRating.id)))).scalar() or 0
    total_raters = (await db.execute(
        select(func.count(func.distinct(CommunityRating.user_id)))
    )).scalar() or 0
    rated_articles = (await db.execute(
        select(func.count(func.distinct(CommunityRating.article_id)))
    )).scalar() or 0

    return {
        "total_ratings": total_ratings,
        "total_raters": total_raters,
        "rated_articles": rated_articles,
    }

"""Rating aggregation service.

Aggregates community ratings per article and story, combining
human ratings with AI scores for a unified bias assessment.
"""

import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.bias_score import BiasScore
from app.models.rating import CommunityRating
from app.models.story import Story

logger = logging.getLogger(__name__)


async def get_article_aggregate_rating(article_id, db: AsyncSession) -> dict | None:
    """Get aggregated community rating for a single article."""
    result = await db.execute(
        select(
            func.count(CommunityRating.id).label("count"),
            func.avg(CommunityRating.political_alignment_rating).label("avg_political"),
            func.avg(CommunityRating.factuality_rating).label("avg_factuality"),
            func.avg(CommunityRating.tone_rating).label("avg_tone"),
            func.avg(CommunityRating.emotional_language_rating).label("avg_emotional"),
        ).where(CommunityRating.article_id == article_id)
    )
    row = result.one()

    if row.count == 0:
        return None

    return {
        "rating_count": row.count,
        "avg_political_alignment": round(float(row.avg_political), 2) if row.avg_political else None,
        "avg_factuality": round(float(row.avg_factuality), 2) if row.avg_factuality else None,
        "avg_tone": round(float(row.avg_tone), 2) if row.avg_tone else None,
        "avg_emotional_language": round(float(row.avg_emotional), 2) if row.avg_emotional else None,
    }


async def get_story_aggregate_rating(story_id, db: AsyncSession) -> dict | None:
    """Get aggregated community rating across all articles in a story."""
    result = await db.execute(
        select(
            func.count(CommunityRating.id).label("count"),
            func.avg(CommunityRating.political_alignment_rating).label("avg_political"),
            func.avg(CommunityRating.factuality_rating).label("avg_factuality"),
            func.avg(CommunityRating.tone_rating).label("avg_tone"),
            func.avg(CommunityRating.emotional_language_rating).label("avg_emotional"),
        )
        .join(Article, CommunityRating.article_id == Article.id)
        .where(Article.story_id == story_id)
    )
    row = result.one()

    if row.count == 0:
        return None

    return {
        "rating_count": row.count,
        "avg_political_alignment": round(float(row.avg_political), 2) if row.avg_political else None,
        "avg_factuality": round(float(row.avg_factuality), 2) if row.avg_factuality else None,
        "avg_tone": round(float(row.avg_tone), 2) if row.avg_tone else None,
        "avg_emotional_language": round(float(row.avg_emotional), 2) if row.avg_emotional else None,
    }


async def get_combined_score(article_id, db: AsyncSession) -> dict:
    """Get combined AI + human score for an article.

    Weights: AI = 0.4, Human = 0.6 (human ratings are more trusted in this system)
    """
    ai_weight = 0.4
    human_weight = 0.6

    # Get AI score
    ai_result = await db.execute(
        select(BiasScore).where(BiasScore.article_id == article_id).limit(1)
    )
    ai_score = ai_result.scalar_one_or_none()

    # Get human aggregate
    human_agg = await get_article_aggregate_rating(article_id, db)

    if not ai_score and not human_agg:
        return {"source": "none", "scores": None}

    if not human_agg:
        return {
            "source": "ai_only",
            "scores": {
                "political_alignment": ai_score.political_alignment,
                "factuality": ai_score.factuality_score,
                "tone": ai_score.tone_score,
                "emotional_language": ai_score.emotional_language_score,
            },
        }

    if not ai_score:
        return {
            "source": "human_only",
            "rating_count": human_agg["rating_count"],
            "scores": {
                "political_alignment": human_agg["avg_political_alignment"],
                "factuality": human_agg["avg_factuality"],
                "tone": human_agg["avg_tone"],
                "emotional_language": human_agg["avg_emotional_language"],
            },
        }

    # Combine: weighted average
    def combine(ai_val, human_val):
        if ai_val is None and human_val is None:
            return None
        if ai_val is None:
            return human_val
        if human_val is None:
            return ai_val
        return round(ai_val * ai_weight + human_val * human_weight, 2)

    return {
        "source": "combined",
        "rating_count": human_agg["rating_count"],
        "scores": {
            "political_alignment": combine(
                ai_score.political_alignment, human_agg["avg_political_alignment"]
            ),
            "factuality": combine(
                ai_score.factuality_score,
                (human_agg["avg_factuality"] - 1) / 4 if human_agg["avg_factuality"] else None,  # normalize 1-5 to 0-1
            ),
            "tone": combine(ai_score.tone_score, human_agg["avg_tone"]),
            "emotional_language": combine(
                ai_score.emotional_language_score,
                (human_agg["avg_emotional_language"] - 1) / 4 if human_agg["avg_emotional_language"] else None,
            ),
        },
    }

"""Feedback endpoints for trusted raters.

Raters can flag article relevance, rate summary accuracy,
and suggest changes to source categorization. Feedback is
stored for later review — it is NOT applied automatically.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.models.feedback import RaterFeedback
from app.models.source import Source
from app.models.story import Story
from app.models.user import User
from app.schemas.feedback import (
    ArticleRelevanceCreate,
    FeedbackResponse,
    SourceCategorizationCreate,
    SummaryRatingCreate,
)

# Reuse the same rater auth dependency from the ratings module
from app.api.v1.ratings import require_rater

router = APIRouter()


@router.post("/article-relevance", response_model=FeedbackResponse)
async def submit_article_relevance(
    body: ArticleRelevanceCreate,
    user: User = Depends(require_rater),
    db: AsyncSession = Depends(get_db),
):
    """Flag whether an article is relevant to a story."""
    # Validate story exists
    story = await db.execute(select(Story).where(Story.id == body.story_id))
    if not story.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Story not found")

    # Validate article exists
    article = await db.execute(select(Article).where(Article.id == body.article_id))
    if not article.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Article not found")

    feedback = RaterFeedback(
        user_id=user.id,
        feedback_type="article_relevance",
        story_id=body.story_id,
        article_id=body.article_id,
        is_relevant=body.is_relevant,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)


@router.post("/summary-rating", response_model=FeedbackResponse)
async def submit_summary_rating(
    body: SummaryRatingCreate,
    user: User = Depends(require_rater),
    db: AsyncSession = Depends(get_db),
):
    """Rate the accuracy of a story's AI-generated summary."""
    # Validate story exists
    story = await db.execute(select(Story).where(Story.id == body.story_id))
    if not story.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Story not found")

    feedback = RaterFeedback(
        user_id=user.id,
        feedback_type="summary_accuracy",
        story_id=body.story_id,
        summary_rating=body.rating,
        summary_correction=body.correction,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)


@router.post("/source-categorization", response_model=FeedbackResponse)
async def submit_source_categorization(
    body: SourceCategorizationCreate,
    user: User = Depends(require_rater),
    db: AsyncSession = Depends(get_db),
):
    """Suggest a change to a source's political categorization."""
    # Validate source exists
    source = await db.execute(select(Source).where(Source.id == body.source_id))
    if not source.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    # Validate alignment value if provided
    valid_alignments = {"state", "semi_state", "independent", "diaspora"}
    if body.suggested_alignment and body.suggested_alignment not in valid_alignments:
        raise HTTPException(
            status_code=422,
            detail=f"suggested_alignment must be one of: {', '.join(sorted(valid_alignments))}",
        )

    feedback = RaterFeedback(
        user_id=user.id,
        feedback_type="source_categorization",
        source_id=body.source_id,
        suggested_alignment=body.suggested_alignment,
        suggested_factional=body.suggested_factional,
        categorization_note=body.note,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)


@router.get("/stats")
async def get_feedback_stats(db: AsyncSession = Depends(get_db)):
    """Public endpoint: aggregate feedback statistics."""
    total = (await db.execute(select(func.count(RaterFeedback.id)))).scalar() or 0

    # Count by type
    type_counts = await db.execute(
        select(RaterFeedback.feedback_type, func.count(RaterFeedback.id))
        .group_by(RaterFeedback.feedback_type)
    )
    by_type = {row[0]: row[1] for row in type_counts.all()}

    # Unique raters who gave feedback
    unique_raters = (await db.execute(
        select(func.count(func.distinct(RaterFeedback.user_id)))
    )).scalar() or 0

    return {
        "total_feedback": total,
        "unique_raters": unique_raters,
        "article_relevance_count": by_type.get("article_relevance", 0),
        "summary_accuracy_count": by_type.get("summary_accuracy", 0),
        "source_categorization_count": by_type.get("source_categorization", 0),
    }

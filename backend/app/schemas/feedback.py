import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ArticleRelevanceCreate(BaseModel):
    story_id: uuid.UUID
    article_id: uuid.UUID
    is_relevant: bool


class SummaryRatingCreate(BaseModel):
    story_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    correction: str | None = None


class SourceCategorizationCreate(BaseModel):
    source_id: uuid.UUID
    suggested_alignment: str | None = None
    suggested_factional: str | None = None
    note: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    feedback_type: str
    story_id: uuid.UUID | None = None
    article_id: uuid.UUID | None = None
    is_relevant: bool | None = None
    summary_rating: int | None = None
    summary_correction: str | None = None
    source_id: uuid.UUID | None = None
    suggested_alignment: str | None = None
    suggested_factional: str | None = None
    categorization_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RatingCreate(BaseModel):
    political_alignment_rating: float | None = Field(None, ge=-2, le=2)
    factuality_rating: float | None = Field(None, ge=1, le=5)
    framing_labels: list[str] = []
    tone_rating: float | None = Field(None, ge=-2, le=2)
    emotional_language_rating: float | None = Field(None, ge=1, le=5)
    notes: str | None = None
    was_blind: bool = True
    time_spent_seconds: int | None = None


class RatingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    article_id: uuid.UUID
    political_alignment_rating: float | None = None
    factuality_rating: float | None = None
    framing_labels: list[str]
    tone_rating: float | None = None
    emotional_language_rating: float | None = None
    notes: str | None = None
    was_blind: bool
    time_spent_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

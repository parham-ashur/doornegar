import uuid
from datetime import datetime

from pydantic import BaseModel


class BiasScoreResponse(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    political_alignment: float | None = None
    pro_regime_score: float | None = None
    reformist_score: float | None = None
    opposition_score: float | None = None
    framing_labels: list[str]
    tone_score: float | None = None
    emotional_language_score: float | None = None
    factuality_score: float | None = None
    source_citation_count: int | None = None
    anonymous_source_count: int | None = None
    uses_loaded_language: bool | None = None
    scoring_method: str
    confidence: float | None = None
    reasoning_en: str | None = None
    reasoning_fa: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

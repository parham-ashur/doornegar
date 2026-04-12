import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.article import ArticleBrief
from app.schemas.bias import BiasScoreResponse


class StoryBrief(BaseModel):
    id: uuid.UUID
    title_en: str
    title_fa: str
    slug: str
    article_count: int
    source_count: int
    covered_by_state: bool
    covered_by_diaspora: bool
    is_blindspot: bool
    blindspot_type: str | None = None
    coverage_diversity_score: float | None = None
    topics: list[str]
    first_published_at: datetime | None = None
    updated_at: datetime | None = None
    trending_score: float
    priority: int = 0
    image_url: str | None = None
    state_pct: int = 0
    diaspora_pct: int = 0
    independent_pct: int = 0

    model_config = {"from_attributes": True}


class StoryArticleWithBias(ArticleBrief):
    source_name_en: str | None = None
    source_name_fa: str | None = None
    source_slug: str | None = None
    source_state_alignment: str | None = None
    bias_scores: list[BiasScoreResponse] = []


class StoryDetail(StoryBrief):
    summary_en: str | None = None
    summary_fa: str | None = None
    articles: list[StoryArticleWithBias] = []


class StoryListResponse(BaseModel):
    stories: list[StoryBrief]
    total: int
    page: int
    page_size: int


class BiasScores(BaseModel):
    tone: float | None = None
    factuality: float | None = None
    emotional_language: float | None = None
    framing: str | list[str] | None = None

class StoryAnalysisResponse(BaseModel):
    story_id: uuid.UUID
    summary_fa: str | None = None
    state_summary_fa: str | None = None
    diaspora_summary_fa: str | None = None
    independent_summary_fa: str | None = None
    bias_explanation_fa: str | None = None
    scores: dict[str, BiasScores | None] | None = None
    # Per-source neutrality scores for 2D spectrum (-1.0 to +1.0)
    source_neutrality: dict[str, float] | None = None
    # Dispute score (0-1) for "most disputed" homepage section
    dispute_score: float | None = None
    # Loaded words per side for "words of the week"
    loaded_words: dict | None = None
    # Deep analyst factors — populated only for premium-tier stories
    analyst: dict | None = None

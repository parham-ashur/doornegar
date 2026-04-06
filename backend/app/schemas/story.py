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
    trending_score: float

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

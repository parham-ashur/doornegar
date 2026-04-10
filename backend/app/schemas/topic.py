import uuid
from datetime import datetime

from pydantic import BaseModel


class TopicCreate(BaseModel):
    title_fa: str
    title_en: str | None = None
    description_fa: str | None = None
    mode: str = "news"  # "news" or "debate"


class TopicUpdate(BaseModel):
    title_fa: str | None = None
    title_en: str | None = None
    description_fa: str | None = None
    mode: str | None = None
    is_active: bool | None = None
    image_url: str | None = None


class AnalystPerspective(BaseModel):
    name_fa: str
    platform: str = "twitter"
    followers: str = ""
    political_leaning: str = "neutral"
    quote_fa: str = ""


class TopicBrief(BaseModel):
    id: uuid.UUID
    title_fa: str
    title_en: str | None = None
    slug: str
    mode: str
    is_auto: bool
    article_count: int
    is_active: bool
    image_url: str | None = None
    has_articles: bool = False
    has_analysts: bool = False
    analysis_fa: str | None = None
    analyzed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TopicAnalysis(BaseModel):
    """Structured analysis result."""
    # News mode fields
    summary_fa: str | None = None
    state_summary_fa: str | None = None
    diaspora_summary_fa: str | None = None
    independent_summary_fa: str | None = None
    bias_explanation_fa: str | None = None
    scores: dict | None = None
    # Debate mode fields
    topic_summary_fa: str | None = None
    positions: list[dict] | None = None
    key_disagreements_fa: list[str] | None = None
    conclusion_fa: str | None = None


class TopicArticleInfo(BaseModel):
    id: uuid.UUID
    title_fa: str | None = None
    title_en: str | None = None
    url: str | None = None
    source_name_fa: str | None = None
    source_state_alignment: str | None = None
    match_confidence: float | None = None
    match_method: str | None = None
    published_at: datetime | None = None


class TopicDetail(TopicBrief):
    description_fa: str | None = None
    analysis: TopicAnalysis | None = None
    analysts: list[AnalystPerspective] = []
    articles: list[TopicArticleInfo] = []


class TopicListResponse(BaseModel):
    topics: list[TopicBrief]
    total: int

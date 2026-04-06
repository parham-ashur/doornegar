import uuid
from datetime import datetime

from pydantic import BaseModel


class ArticleBrief(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    story_id: uuid.UUID | None = None
    title_original: str
    title_en: str | None = None
    title_fa: str | None = None
    url: str
    summary: str | None = None
    image_url: str | None = None
    author: str | None = None
    language: str
    published_at: datetime | None = None
    ingested_at: datetime

    model_config = {"from_attributes": True}


class ArticleDetail(ArticleBrief):
    content_text: str | None = None
    categories: list[str]
    keywords: list[str]
    named_entities: list[dict]
    sentiment_score: float | None = None
    processed_at: datetime | None = None


class ArticleListResponse(BaseModel):
    articles: list[ArticleBrief]
    total: int
    page: int
    page_size: int

import uuid
from datetime import datetime

from pydantic import BaseModel


class SourceBase(BaseModel):
    name_en: str
    name_fa: str
    slug: str
    website_url: str
    state_alignment: str
    irgc_affiliated: bool = False
    production_location: str
    factional_alignment: str | None = None
    language: str = "fa"


class SourceResponse(SourceBase):
    id: uuid.UUID
    rss_urls: list[str]
    logo_url: str | None = None
    is_active: bool
    credibility_score: float | None = None
    description_en: str | None = None
    description_fa: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    sources: list[SourceResponse]
    total: int

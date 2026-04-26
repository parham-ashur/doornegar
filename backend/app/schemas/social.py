import uuid
from datetime import datetime

from pydantic import BaseModel


class TelegramChannelCreate(BaseModel):
    username: str
    title: str
    description: str | None = None
    channel_type: str = "news"
    political_leaning: str | None = None
    language: str = "fa"


class TelegramChannelResponse(BaseModel):
    id: uuid.UUID
    username: str
    title: str
    description: str | None = None
    channel_type: str
    political_leaning: str | None = None
    subscriber_count: int | None = None
    language: str
    is_active: bool
    last_fetched_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TelegramChannelLite(BaseModel):
    """Minimal channel info embedded inside post responses so the
    frontend can render the channel label and build the deep link
    (https://t.me/{username}/{message_id}) without a second round-trip."""

    username: str
    title: str
    channel_type: str

    model_config = {"from_attributes": True}


class TelegramPostResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    story_id: uuid.UUID | None = None
    message_id: int
    text: str | None = None
    date: datetime
    views: int | None = None
    forwards: int | None = None
    reply_count: int | None = None
    urls: list[str]
    sentiment_score: float | None = None
    framing_labels: list[str]
    keywords: list[str]
    shares_news_link: bool
    is_commentary: bool
    created_at: datetime
    channel: TelegramChannelLite | None = None

    model_config = {"from_attributes": True}


class SocialSentimentResponse(BaseModel):
    story_id: uuid.UUID
    total_posts: int
    total_views: int
    total_forwards: int
    unique_channels: int
    avg_sentiment: float | None = None
    positive_count: int
    negative_count: int
    neutral_count: int
    framing_distribution: dict[str, int]
    snapshot_at: datetime

    model_config = {"from_attributes": True}


class StoryPostsResponse(BaseModel):
    story_id: uuid.UUID
    posts: list[TelegramPostResponse]
    sentiment: SocialSentimentResponse | None = None
    total_posts: int

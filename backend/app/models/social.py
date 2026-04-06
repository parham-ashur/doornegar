"""Social media models for tracking Telegram channel posts and their relation to news stories."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TelegramChannel(Base):
    """A public Telegram channel that discusses Iranian news."""

    __tablename__ = "telegram_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    channel_type: Mapped[str] = mapped_column(
        String(20),
        comment="news | commentary | activist | political_party | citizen | aggregator",
    )
    political_leaning: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="pro_regime | reformist | opposition | monarchist | left | neutral",
    )
    subscriber_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="fa")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tracking
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Telegram message ID of last fetched post"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    posts: Mapped[list["TelegramPost"]] = relationship(back_populates="channel")

    def __repr__(self) -> str:
        return f"<TelegramChannel @{self.username}>"


class TelegramPost(Base):
    """A single post from a Telegram channel, potentially linked to a news story."""

    __tablename__ = "telegram_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telegram_channels.id"), index=True
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), nullable=True, index=True
    )

    # Telegram data
    message_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forwards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Links found in the post (URLs to news articles)
    urls: Mapped[dict] = mapped_column(JSONB, default=list)

    # NLP analysis
    sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="-1 negative to +1 positive"
    )
    framing_labels: Mapped[dict] = mapped_column(JSONB, default=list)
    keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    # embedding field removed for MVP — not needed without sentence-transformers

    # Flags
    shares_news_link: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Post contains a link to a known news article"
    )
    is_commentary: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Post is commentary/analysis rather than news sharing"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    channel: Mapped["TelegramChannel"] = relationship(back_populates="posts")
    story: Mapped["Story | None"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),
    )

    def __repr__(self) -> str:
        return f"<TelegramPost channel={self.channel_id} msg={self.message_id}>"


class SocialSentimentSnapshot(Base):
    """Aggregated social media sentiment for a story at a point in time.

    Stores periodic snapshots so we can track how sentiment evolves.
    """

    __tablename__ = "social_sentiment_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), index=True
    )

    # Aggregate metrics
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    total_views: Mapped[int] = mapped_column(Integer, default=0)
    total_forwards: Mapped[int] = mapped_column(Integer, default=0)
    unique_channels: Mapped[int] = mapped_column(Integer, default=0)

    # Sentiment distribution
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)

    # Framing distribution — how social media frames the story
    framing_distribution: Mapped[dict] = mapped_column(
        JSONB, default=dict, comment='{"conflict": 5, "human_rights": 3, ...}'
    )

    # Narrative analysis
    dominant_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_divergence: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="0-1: how much social media framing differs from news media framing",
    )

    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SocialSentiment story={self.story_id} posts={self.total_posts}>"

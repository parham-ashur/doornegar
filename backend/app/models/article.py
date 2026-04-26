import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), index=True
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), nullable=True, index=True
    )

    # Content
    title_original: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_fa: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Classification
    language: Mapped[str] = mapped_column(String(5), default="fa")
    categories: Mapped[dict] = mapped_column(JSONB, default=list)
    # Raw category/section captured from RSS feedparser entry. Used as a
    # weak signal for content-type classification.
    rss_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Content-type classifier verdict — gates downstream NLP. One of:
    # news, opinion, discussion, aggregation, other, unclassified.
    # Only labels in Source.content_filters['allowed'] reach NLP.
    content_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    content_type_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # NLP outputs
    # embedding stored as JSON array for MVP (pgvector not required)
    embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    named_entities: Mapped[dict] = mapped_column(JSONB, default=list)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Reliability / backoff flags
    # Set when an LLM call (bias scoring) fails; skipped on retry for 24h
    llm_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when step_fix_images last HEAD-checked this article's image_url;
    # checks within the last 24h are skipped to avoid wasted HTTP calls
    image_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # How many times this article has been sent to cluster_new without
    # joining a viable (≥5-article) group. Articles at the max (3) are
    # skipped on future runs — prevents orphan articles from being
    # re-sent to the LLM forever.
    cluster_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="articles")  # noqa: F821
    story: Mapped["Story | None"] = relationship(back_populates="articles")  # noqa: F821
    bias_scores: Mapped[list["BiasScore"]] = relationship(back_populates="article")  # noqa: F821
    community_ratings: Mapped[list["CommunityRating"]] = relationship(  # noqa: F821
        back_populates="article"
    )

    __table_args__ = (
        Index("idx_articles_published", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Article {self.url[:60]}>"

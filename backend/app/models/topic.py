import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title_fa: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description_fa: Mapped[str | None] = mapped_column(Text, nullable=True)

    # news or debate
    mode: Mapped[str] = mapped_column(String(20), default="news")

    # auto-detected vs manually created
    is_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # LLM analysis
    analysis_fa: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analyst_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Display
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metrics
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    topic_articles: Mapped[list["TopicArticle"]] = relationship(back_populates="topic")

    def __repr__(self) -> str:
        return f"<Topic {self.slug} mode={self.mode}>"


class TopicArticle(Base):
    __tablename__ = "topic_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id"), index=True
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), index=True
    )
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    topic: Mapped["Topic"] = relationship(back_populates="topic_articles")
    article: Mapped["Article"] = relationship()  # noqa: F821

    __table_args__ = (
        # Unique constraint: one article per topic
        {"comment": "Junction table linking topics to articles"},
    )

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Headlines
    title_en: Mapped[str] = mapped_column(Text)
    title_fa: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_fa: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aggregated metrics
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)

    # Coverage analysis
    covered_by_state: Mapped[bool] = mapped_column(Boolean, default=False)
    covered_by_diaspora: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_diversity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_blindspot: Mapped[bool] = mapped_column(Boolean, default=False)
    blindspot_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="state_only | diaspora_only | single_source"
    )

    # Categorization
    topics: Mapped[dict] = mapped_column(JSONB, default=list)

    # Time tracking
    first_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trending_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="Manual priority: higher = more prominent. 0=auto")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Reliability flag: set when summary generation fails; story is skipped for 24h before retry
    llm_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    articles: Mapped[list["Article"]] = relationship(back_populates="story")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Story {self.slug}>"

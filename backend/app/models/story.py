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

    # View tracking
    view_count: Mapped[int] = mapped_column(Integer, default=0)

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
    # Set to True when an admin has hand-edited any of: title_fa, title_en,
    # state_summary_fa, diaspora_summary_fa, bias_explanation_fa. When set,
    # the maintenance pipeline skips regeneration for this story so manual
    # edits are preserved.
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Mean of all article embeddings in this story. Used by the clustering
    # pre-filter to quickly find candidate stories for new articles via
    # cosine similarity (avoids sending irrelevant stories to the LLM).
    centroid_embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    telegram_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Cached deep Telegram discourse analysis")
    editorial_context_fa: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Niloofar editorial background context in Farsi")
    # Snapshot of the analysis axes (dispute_score, inside/outside pct, bias
    # hash, article_count) captured at the end of every nightly maintenance
    # run. Used by app/services/story_freshness.py to decide whether a
    # story has changed meaningfully since ~20-24h ago. Powers the homepage
    # "بروزرسانی" badge and the "hero can repeat only on significant change"
    # rule. See step_snapshot_analyses in auto_maintenance.py.
    analysis_snapshot_24h: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Nightly snapshot for daily-change detection")
    # Hourly update signal — written by step_detect_hourly_updates when
    # a story gains articles in the last hour AND a trigger fires
    # (side flip, coverage shift ≥15pp, burst of ≥2 articles). Shape:
    #   {"has_update": bool, "kind": "side_flip"|"coverage_shift"|"burst",
    #    "reason_fa": str, "detected_at": ISO8601}
    # The API prefers this over the 24h-snapshot-derived signal when
    # detected_at is within the last 4 hours, falling back to the
    # snapshot afterwards. Powers the same "بروزرسانی" badge but with
    # intra-day granularity.
    hourly_update_signal: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Hourly detected-update signal (4h TTL on UI)")

    # Relationships
    articles: Mapped[list["Article"]] = relationship(back_populates="story")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Story {self.slug}>"

"""Analyst take model — LLM-extracted insights from analyst Telegram posts."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AnalystTake(Base):
    """A structured insight extracted from an analyst's Telegram post.

    Each take represents one analyst's argument or claim about a news story,
    extracted by LLM from their Telegram channel posts.
    """

    __tablename__ = "analyst_takes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analyst_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysts.id"), nullable=True, index=True
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), nullable=True, index=True
    )
    telegram_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telegram_posts.id"), nullable=True, index=True
    )

    # Content
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_fa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    key_claim: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Classification
    take_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="prediction | reasoning | insider_signal | fact_check | historical_parallel | commentary",
    )
    confidence_direction: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="bullish | bearish | neutral",
    )

    # Verification (filled later)
    verified_later: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    analyst: Mapped["Analyst | None"] = relationship()  # noqa: F821
    story: Mapped["Story | None"] = relationship()  # noqa: F821
    telegram_post: Mapped["TelegramPost | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<AnalystTake {self.take_type} analyst={self.analyst_id} story={self.story_id}>"

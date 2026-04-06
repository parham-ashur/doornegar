import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BiasScore(Base):
    __tablename__ = "bias_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), index=True
    )

    # Political alignment
    political_alignment: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="-1 pro-regime to +1 opposition"
    )
    pro_regime_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reformist_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    opposition_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Framing
    framing_labels: Mapped[dict] = mapped_column(JSONB, default=list)
    tone_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="-1 negative to +1 positive"
    )
    emotional_language_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0 factual to 1 loaded"
    )

    # Credibility signals
    factuality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anonymous_source_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses_loaded_language: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Methodology
    scoring_method: Mapped[str] = mapped_column(
        String(20), comment="llm_initial | llm_refined | crowd_validated"
    )
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Reasoning (for transparency)
    reasoning_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_fa: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    article: Mapped["Article"] = relationship(back_populates="bias_scores")  # noqa: F821

    def __repr__(self) -> str:
        return f"<BiasScore article={self.article_id} method={self.scoring_method}>"

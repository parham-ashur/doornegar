import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RaterFeedback(Base):
    __tablename__ = "rater_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    feedback_type: Mapped[str] = mapped_column(
        String(30),
        comment="article_relevance | summary_accuracy | source_categorization",
    )

    # For article relevance
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id"), nullable=True, index=True
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True, index=True
    )
    is_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # For summary accuracy
    summary_rating: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="1-5")
    summary_correction: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For source categorization
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True, index=True
    )
    suggested_alignment: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="state | semi_state | independent | diaspora"
    )
    suggested_factional: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="hardline | principlist | reformist | moderate | opposition | monarchist | left",
    )
    categorization_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship()  # noqa: F821
    story: Mapped["Story | None"] = relationship()  # noqa: F821
    article: Mapped["Article | None"] = relationship()  # noqa: F821
    source: Mapped["Source | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<RaterFeedback {self.feedback_type} user={self.user_id}>"

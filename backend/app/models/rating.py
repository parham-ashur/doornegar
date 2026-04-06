import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CommunityRating(Base):
    __tablename__ = "community_ratings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), index=True
    )

    # Rating dimensions
    political_alignment_rating: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="-2 to +2"
    )
    factuality_rating: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="1-5"
    )
    framing_labels: Mapped[dict] = mapped_column(JSONB, default=list)
    tone_rating: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="-2 to +2"
    )
    emotional_language_rating: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="1-5"
    )

    # Free text
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rating context
    was_blind: Mapped[bool] = mapped_column(Boolean, default=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="ratings")  # noqa: F821
    article: Mapped["Article"] = relationship(back_populates="community_ratings")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_user_article_rating"),
    )

    def __repr__(self) -> str:
        return f"<CommunityRating user={self.user_id} article={self.article_id}>"

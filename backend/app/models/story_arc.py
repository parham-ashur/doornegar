import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StoryArc(Base):
    """A curated story arc — ordered chapters that form one narrative journey.

    Arcs are created manually from the HITL suggester (which proposes
    candidate arcs via centroid cosine clustering on visible stories).
    Membership and order live on Story.arc_id + Story.arc_order; this
    table holds the arc-level identity (title, description).
    """

    __tablename__ = "story_arcs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title_fa: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description_fa: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

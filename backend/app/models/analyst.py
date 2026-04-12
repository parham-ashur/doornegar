import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Analyst(Base):
    __tablename__ = "analysts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_en: Mapped[str] = mapped_column(String(255))
    name_fa: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # Platform presence
    telegram_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    twitter_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    political_leaning: Mapped[str] = mapped_column(
        String(30), comment="reformist | conservative | independent | opposition | academic"
    )
    location: Mapped[str] = mapped_column(
        String(20), comment="inside_iran | outside_iran"
    )
    affiliation: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Description
    focus_areas: Mapped[dict] = mapped_column(JSONB, default=list)
    bio_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_fa: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_imprisoned: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Analyst {self.slug} ({self.political_leaning})>"

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_en: Mapped[str] = mapped_column(String(255))
    name_fa: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    website_url: Mapped[str] = mapped_column(Text)
    rss_urls: Mapped[dict] = mapped_column(JSONB, default=list)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Iranian-specific classification
    state_alignment: Mapped[str] = mapped_column(
        String(20), comment="state | semi_state | independent | diaspora"
    )
    irgc_affiliated: Mapped[bool] = mapped_column(Boolean, default=False)
    production_location: Mapped[str] = mapped_column(
        String(20), comment="inside_iran | outside_iran"
    )
    factional_alignment: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="hardline | principlist | reformist | moderate | opposition | monarchist | left",
    )

    # Metadata
    language: Mapped[str] = mapped_column(String(5), default="fa")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    credibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_fa: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    articles: Mapped[list["Article"]] = relationship(back_populates="source")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Source {self.slug} ({self.state_alignment})>"

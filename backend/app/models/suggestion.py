"""SourceSuggestion — user-submitted suggestions for new sources to track.

Public visitors can submit suggestions via a form. Admins review them and
decide whether to add the source to the platform. No data flows into the
sources table automatically — everything goes through manual review.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceSuggestion(Base):
    __tablename__ = "source_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # What the user suggested
    suggestion_type: Mapped[str] = mapped_column(
        String(20),
        comment="media | telegram | x_twitter | youtube | instagram | website | other",
    )
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, comment="URL or handle (e.g., @username)")
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    suggested_category: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="state | semi_state | independent | diaspora | not_sure",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Submitter info (optional)
    submitter_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitter_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitter_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review status
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="pending | approved | rejected | duplicate | already_tracked",
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Salted hash of submitter IP, used only for rate limiting — not personal data
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

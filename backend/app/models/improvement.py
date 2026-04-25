"""ImprovementFeedback — rater suggestions to improve content/design.

Raters browse the site and flag things that should be changed: wrong
titles, bad images, incorrect clustering, missing context, layout
issues, etc. Each submission becomes a todo item in the admin dashboard
that Parham reviews and either implements, delegates to Claude, or
dismisses.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImprovementFeedback(Base):
    __tablename__ = "improvement_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # What is being suggested for improvement
    target_type: Mapped[str] = mapped_column(
        String(30),
        comment="story | story_title | story_image | story_summary | article | source | layout | homepage | other",
    )
    target_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="ID of the specific item (story_id, article_id, etc.) when applicable",
    )
    target_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Page URL where the rater saw the issue",
    )

    # The issue
    issue_type: Mapped[str] = mapped_column(
        String(30),
        comment="wrong_title | bad_image | wrong_clustering | bad_summary | wrong_source_class | layout_issue | bug | feature_request | other",
    )
    current_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Current value or a snapshot of what the rater saw",
    )
    suggested_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="What the rater thinks it should be",
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rater info
    rater_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rater_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Auto-captured device context: "mobile 375×812" or "desktop 1440×900" + user agent
    device_info: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Soft fingerprint of submitter (sha256 of IP + UA + accept-language,
    # truncated). Anonymous «نامرتبط» votes are deduped by this so one
    # person can't trip the 3-fingerprint auto-orphan threshold alone.
    # NULL on rows from before the column existed — those won't count
    # toward consensus.
    submitter_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Admin tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        comment="open | in_progress | done | wont_do | duplicate",
    )
    priority: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="low | medium | high",
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

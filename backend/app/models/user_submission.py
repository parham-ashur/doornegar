"""UserSubmission — public content submissions tied to a story.

Readers submit articles, Telegram posts, Instagram excerpts, or other
raw source material via a public form at /[locale]/submit. Each
submission can optionally link to an existing story on the homepage;
unlinked submissions become Niloofar's queue to review and attach (or
create a new cluster).

Kept separate from ImprovementFeedback because:
  - payload is larger (full text, not a single-line suggestion)
  - workflow is different (accept-as-article, accept-as-post, spawn-new-cluster)
  - the submitter is a content contributor, not a site rater
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSubmission(Base):
    __tablename__ = "user_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # What kind of content is this
    submission_type: Mapped[str] = mapped_column(
        String(20),
        comment="article | telegram_post | instagram_post | news | other",
    )

    # Optional story link — if set, submitter is saying "this goes with
    # story X". Admin/Niloofar can accept the link, move it, or reject.
    suggested_story_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="UUID of the story the submitter wants this attached to",
    )

    # Core payload
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment='e.g., "BBC Persian", "@iran_int_tv", "Instagram - reporter_xyz"',
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Telegram-specific (only populated when submission_type=telegram_post)
    channel_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram channel @username without @",
    )
    is_analyst: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if submitter thinks the channel is analyst commentary, False if news feed, None if unsure",
    )

    # Display language of the content (for downstream NLP routing)
    language: Mapped[str] = mapped_column(String(5), default="fa")

    # Submitter info (all optional — anonymous submissions allowed)
    submitter_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitter_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitter_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Free-text note from submitter — why this matters, how they found it, etc.",
    )

    # Admin review
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="pending | accepted_article | accepted_post | rejected | duplicate",
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Anti-spam / audit
    submitter_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

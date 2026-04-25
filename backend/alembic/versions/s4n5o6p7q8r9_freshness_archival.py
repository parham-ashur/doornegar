"""freshness + archival columns

Revision ID: s4n5o6p7q8r9
Revises: r3m4n5o6p7q8
Create Date: 2026-04-25 22:30:00.000000

Why:
- Stories older than ~30 days lose editorial relevance. archived_at
  lets the homepage / blindspots / trending APIs filter dead threads
  out without deleting the rows (direct URLs + SEO still work).
- request_fingerprint adds a long-lived cookie hash to anon feedback
  so the 3-fingerprint dedupe can't be bypassed with a private-mode
  reload. Indexed for the partial improvement_feedback dedupe query.
- New event_types are emitted by the maintenance cron to track loop
  health. No schema change needed for events themselves; this
  migration just documents the new types and adds an index that
  speeds the /dashboard/learning event filter when grouping by type.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "s4n5o6p7q8r9"
down_revision: Union[str, None] = "r3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # F3 — story archival
    op.execute(
        "ALTER TABLE stories "
        "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_archived_at "
        "ON stories(archived_at) "
        "WHERE archived_at IS NOT NULL"
    )

    # #5 — cookie fingerprint column on improvement_feedback. Layered on
    # top of the existing submitter_fingerprint (IP + UA + accept-lang)
    # introduced in q2l3m4n5o6p7. Both feed the same dedupe set; this
    # one is harder to bypass.
    op.execute(
        "ALTER TABLE improvement_feedback "
        "ADD COLUMN IF NOT EXISTS submitter_cookie VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_improvement_cookie_target "
        "ON improvement_feedback(target_id, submitter_cookie) "
        "WHERE submitter_cookie IS NOT NULL"
    )

    # #9 — index on story_events.event_type so /dashboard/learning's
    # group-by-type queries don't seq-scan a growing table.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_events_type_created "
        "ON story_events(event_type, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_story_events_type_created")
    op.execute("DROP INDEX IF EXISTS idx_improvement_cookie_target")
    op.execute("ALTER TABLE improvement_feedback DROP COLUMN IF EXISTS submitter_cookie")
    op.execute("DROP INDEX IF EXISTS idx_stories_archived_at")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS archived_at")

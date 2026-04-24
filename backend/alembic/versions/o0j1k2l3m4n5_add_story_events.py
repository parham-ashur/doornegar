"""add story_events log table

Revision ID: o0j1k2l3m4n5
Revises: n9i0j1k2l3m4
Create Date: 2026-04-24 10:00:00.000000

Why:
- Unified event log for clustering decisions (decision queue) and
  field-level story edits (audit trail). One table so the forthcoming
  HITL UI reads a single stream instead of stitching N logs together.
- Columns are wide enough to carry confidence/signals for clustering
  decisions and field/old_value/new_value for audit entries without a
  second table.
- Idempotent IF NOT EXISTS pattern so app/main.py startup self-heal is
  safe on a fresh deploy.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "o0j1k2l3m4n5"
down_revision: Union[str, None] = "n9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS story_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            story_id UUID,
            article_id UUID,
            event_type VARCHAR(40) NOT NULL,
            actor VARCHAR(40) NOT NULL,
            field VARCHAR(60),
            old_value TEXT,
            new_value TEXT,
            confidence DOUBLE PRECISION,
            signals JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_events_story "
        "ON story_events(story_id, created_at DESC) "
        "WHERE story_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_events_type "
        "ON story_events(event_type, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_events_article "
        "ON story_events(article_id) "
        "WHERE article_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_story_events_article")
    op.execute("DROP INDEX IF EXISTS idx_story_events_type")
    op.execute("DROP INDEX IF EXISTS idx_story_events_story")
    op.execute("DROP TABLE IF EXISTS story_events")

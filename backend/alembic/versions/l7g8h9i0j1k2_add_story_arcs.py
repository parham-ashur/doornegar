"""add story_arcs table + Story.arc_id/arc_order

Revision ID: l7g8h9i0j1k2
Revises: k6f7g8h9i0j1
Create Date: 2026-04-20 14:00:00.000000

Why:
- HITL arc suggester (/dashboard/hitl/arcs) lets a curator group related
  stories into one narrative journey (e.g. ceasefire arc: blockade →
  talks → reopening). Membership + chronological order live directly on
  Story; arc identity (title, slug, description) lives in story_arcs.
- Idempotent IF NOT EXISTS so the app/main.py startup self-heal can be
  a no-op in environments where the migration already ran.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'l7g8h9i0j1k2'
down_revision: Union[str, None] = 'k6f7g8h9i0j1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS story_arcs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title_fa TEXT NOT NULL,
            title_en TEXT,
            slug VARCHAR(200) NOT NULL UNIQUE,
            description_fa TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_story_arcs_slug ON story_arcs(slug)")
    op.execute("ALTER TABLE stories ADD COLUMN IF NOT EXISTS arc_id UUID")
    op.execute("ALTER TABLE stories ADD COLUMN IF NOT EXISTS arc_order INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stories_arc_id ON stories(arc_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stories_arc_id")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS arc_order")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS arc_id")
    op.execute("DROP TABLE IF EXISTS story_arcs")

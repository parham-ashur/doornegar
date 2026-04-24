"""add freeze + split + review tier to stories

Revision ID: n9i0j1k2l3m4
Revises: m8h9i0j1k2l3
Create Date: 2026-04-24 09:00:00.000000

Why:
- Clustering guardrails: flag stories as they grow past 100/3d, 150/5d,
  and 200/7d thresholds so HITL can review and optionally freeze them
  before they become dumping-ground mega-clusters (bfd468e0 pattern).
- Freeze gate: matcher + merge steps skip stories with frozen_at set,
  so a reviewed story stops absorbing new articles.
- Split tracking: split_from_id points children back at the story they
  were carved out of, for audit + UI breadcrumbs.
- Idempotent IF NOT EXISTS so app/main.py startup self-heal is safe.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "n9i0j1k2l3m4"
down_revision: Union[str, None] = "m8h9i0j1k2l3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories "
        "ADD COLUMN IF NOT EXISTS frozen_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE stories "
        "ADD COLUMN IF NOT EXISTS split_from_id UUID"
    )
    op.execute(
        "ALTER TABLE stories "
        "ADD COLUMN IF NOT EXISTS review_tier SMALLINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_unfrozen "
        "ON stories(updated_at) WHERE frozen_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_review_tier "
        "ON stories(review_tier) WHERE review_tier > 0 AND frozen_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stories_review_tier")
    op.execute("DROP INDEX IF EXISTS idx_stories_unfrozen")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS review_tier")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS split_from_id")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS frozen_at")

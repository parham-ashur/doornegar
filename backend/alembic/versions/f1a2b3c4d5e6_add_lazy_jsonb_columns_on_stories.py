"""add lazy JSONB columns on stories (editorial_context_fa, analysis_snapshot_24h)

Revision ID: f1a2b3c4d5e6
Revises: e9f7a3d5c8b1
Create Date: 2026-04-17 18:00:00.000000

Why:
- Both columns were introduced by "self-creating via ALTER TABLE IF NOT EXISTS"
  inside nightly maintenance steps (editorial_context_fa via
  step_niloofar_editorial, analysis_snapshot_24h via step_snapshot_analyses).
  On a fresh deploy that hasn't had a nightly run yet, the column exists on
  the SQLAlchemy model (app/models/story.py) but not in Postgres, so every
  SELECT on `stories` fails with a 500. We hit this today — the homepage
  blindspot section went empty because /api/v1/stories/* was broken until the
  self-heal ran. This migration backstops that pattern for existing deploys.
- IF NOT EXISTS keeps it idempotent: environments where the maintenance step
  already created the column are no-ops.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e9f7a3d5c8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS editorial_context_fa JSONB"
    )
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS analysis_snapshot_24h JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS analysis_snapshot_24h")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS editorial_context_fa")

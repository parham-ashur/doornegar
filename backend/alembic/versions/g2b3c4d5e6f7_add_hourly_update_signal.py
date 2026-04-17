"""add hourly_update_signal JSONB on stories

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-17 21:15:00.000000

Why:
- New step_detect_hourly_updates runs in the hourly rss-cron and writes a
  signal here when a story gains articles in the past hour AND a trigger
  fires (side flip, coverage shift ≥ 15pp, burst of ≥5 articles). The API
  prefers this over the 24h-snapshot signal when fresh (<2h), so the
  homepage "بروزرسانی" badge can reflect intra-day developments.
- Idempotent IF NOT EXISTS so environments where app/main.py's startup
  self-heal already created the column are no-ops.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS hourly_update_signal JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS hourly_update_signal")

"""add content_hash index on user_submissions

Revision ID: k6f7g8h9i0j1
Revises: j5e6f7g8h9i0
Create Date: 2026-04-19 10:00:00.000000

Why:
- Dedup check at POST /api/v1/submissions needs a fast exact-match
  lookup on normalized content. Storing a SHA-256 of the normalized
  text lets us index it as a plain VARCHAR(64) instead of scanning
  full content text on every request.
- Idempotent ADD COLUMN / CREATE INDEX IF NOT EXISTS.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "k6f7g8h9i0j1"
down_revision: Union[str, None] = "j5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_submissions ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_submissions_content_hash "
        "ON user_submissions (content_hash)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_submissions_content_hash")
    op.execute("ALTER TABLE user_submissions DROP COLUMN IF EXISTS content_hash")

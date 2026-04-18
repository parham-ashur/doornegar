"""extend user_submissions with image_url + published_at; drop submitter name/contact

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-04-18 22:15:00.000000

Why:
- Image URL and published-at are high-signal fields for the submission
  flow (cover image for the story, freshness signal for clustering),
  while submitter name/contact were cut per Parham's feedback — we
  don't want to nudge readers into leaving identifying info.
- Idempotent ADD COLUMN / DROP COLUMN IF EXISTS so re-running is safe.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "j5e6f7g8h9i0"
down_revision: Union[str, None] = "i4d5e6f7g8h9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_submissions ADD COLUMN IF NOT EXISTS image_url TEXT")
    op.execute(
        "ALTER TABLE user_submissions ADD COLUMN IF NOT EXISTS published_at "
        "TIMESTAMP WITH TIME ZONE"
    )
    # The two submitter-identity columns are now unused by the public form
    # but stay nullable on the DB so legacy rows don't break. Leave them
    # in place for audit; we just stop writing to them.


def downgrade() -> None:
    op.execute("ALTER TABLE user_submissions DROP COLUMN IF EXISTS image_url")
    op.execute("ALTER TABLE user_submissions DROP COLUMN IF EXISTS published_at")

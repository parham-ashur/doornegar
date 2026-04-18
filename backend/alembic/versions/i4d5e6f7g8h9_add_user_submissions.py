"""add user_submissions table

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-04-18 21:30:00.000000

Why:
- Public content submission form at /[locale]/submit lets readers paste an
  article, telegram post, instagram excerpt, or other raw source material
  and optionally link it to an existing story. Pending queue feeds the
  HITL review loop.
- Idempotent IF NOT EXISTS so re-running on an env where the table was
  already created (e.g. via app boot) is a no-op.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'i4d5e6f7g8h9'
down_revision: Union[str, None] = 'h3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_type VARCHAR(20) NOT NULL,
            suggested_story_id VARCHAR(40),
            title TEXT,
            content TEXT NOT NULL,
            source_name VARCHAR(255),
            source_url TEXT,
            channel_username VARCHAR(100),
            is_analyst BOOLEAN,
            language VARCHAR(5) NOT NULL DEFAULT 'fa',
            submitter_name VARCHAR(100),
            submitter_contact VARCHAR(200),
            submitter_note TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            admin_notes TEXT,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            submitter_ip VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_submissions_status "
        "ON user_submissions (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_submissions_story "
        "ON user_submissions (suggested_story_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_submissions")

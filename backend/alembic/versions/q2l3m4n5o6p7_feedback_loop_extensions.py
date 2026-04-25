"""add feedback loop extensions

Revision ID: q2l3m4n5o6p7
Revises: p1k2l3m4n5o6
Create Date: 2026-04-25 19:30:00.000000

Why:
- improvement_feedback.submitter_fingerprint enables soft dedup of
  anonymous «نامرتبط» votes (hash of IP + UA + accept-language).
  Without it, one person could click 3 times and trigger auto-orphan.
- rater_feedback.applied_at tracks which summary-correction rows have
  been processed by step_apply_summary_corrections so the same
  correction doesn't re-apply on every maintenance tick.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "q2l3m4n5o6p7"
down_revision: Union[str, None] = "p1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE improvement_feedback "
        "ADD COLUMN IF NOT EXISTS submitter_fingerprint VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_improvement_fp_target "
        "ON improvement_feedback(target_id, submitter_fingerprint) "
        "WHERE submitter_fingerprint IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE rater_feedback "
        "ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_improvement_fp_target")
    op.execute("ALTER TABLE improvement_feedback DROP COLUMN IF EXISTS submitter_fingerprint")
    op.execute("ALTER TABLE rater_feedback DROP COLUMN IF EXISTS applied_at")

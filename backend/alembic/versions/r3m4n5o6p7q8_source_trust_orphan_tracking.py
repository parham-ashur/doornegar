"""add source trust score + orphan-from tracking

Revision ID: r3m4n5o6p7q8
Revises: q2l3m4n5o6p7
Create Date: 2026-04-25 20:30:00.000000

Why:
- sources.cluster_quality_score lets feedback shape clustering: sources
  whose articles are flagged as off-topic at >3× the median rate get a
  stricter cosine threshold (effective_threshold / score) when the
  matcher considers them. Floored at 0.5 so one bad week can't
  permanently sink a source.
- improvement_feedback.orphaned_from_story_id closes the negative-pair
  loop for anonymous «نامرتبط» votes. Without it, the clusterer can
  re-attach the same article to the same wrong story right after the
  3-fingerprint auto-orphan fires.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "r3m4n5o6p7q8"
down_revision: Union[str, None] = "q2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sources "
        "ADD COLUMN IF NOT EXISTS cluster_quality_score "
        "DOUBLE PRECISION NOT NULL DEFAULT 1.0"
    )
    op.execute(
        "ALTER TABLE improvement_feedback "
        "ADD COLUMN IF NOT EXISTS orphaned_from_story_id UUID"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_improvement_orphan_pair "
        "ON improvement_feedback(target_id, orphaned_from_story_id) "
        "WHERE orphaned_from_story_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_improvement_orphan_pair")
    op.execute("ALTER TABLE improvement_feedback DROP COLUMN IF EXISTS orphaned_from_story_id")
    op.execute("ALTER TABLE sources DROP COLUMN IF EXISTS cluster_quality_score")

"""add audit_notes JSONB on stories (cluster-drift + future audit flags)

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-04-18 09:00:00.000000

Why:
- Phase 3 of the clustering upgrade — step_audit_cluster_coherence writes
  per-story drift notes under audit_notes.cluster_drift when sampled pairs
  fall below a cosine floor. Niloofar surfaces these in the next audit.
- Idempotent IF NOT EXISTS so environments where audit_cluster_coherence
  has already self-healed the column are no-ops.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'h3c4d5e6f7g8'
down_revision: Union[str, None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS audit_notes JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS audit_notes")

"""add cluster_attempts to articles

Revision ID: m8h9i0j1k2l3
Revises: l7g8h9i0j1k2
Create Date: 2026-04-22 12:00:00.000000

Why:
- Orphan articles (story_id IS NULL that never reach the 5-article floor)
  were being re-sent to cluster_new on every pipeline run, driving ~7×
  article-slot replay. Counter lets us skip articles that have already
  failed to cluster N times.
- Idempotent IF NOT EXISTS so app/main.py startup self-heal is a no-op
  where the migration already ran.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'm8h9i0j1k2l3'
down_revision: Union[str, None] = 'l7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE articles "
        "ADD COLUMN IF NOT EXISTS cluster_attempts INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_unclustered_retry "
        "ON articles(ingested_at) "
        "WHERE story_id IS NULL AND cluster_attempts < 3"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_unclustered_retry")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS cluster_attempts")

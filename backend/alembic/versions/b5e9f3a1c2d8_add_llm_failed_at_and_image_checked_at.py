"""add llm_failed_at on articles + stories, image_checked_at on articles

Revision ID: b5e9f3a1c2d8
Revises: 0a7c08d01fe5
Create Date: 2026-04-11 23:00:00.000000

Why:
- llm_failed_at: when bias scoring or story summarization raises an
  exception, we set this column so the maintenance pipeline skips
  the item for 24h. Prevents retry-forever loops on articles/stories
  that have broken content or stale URLs (wastes money + time).
- image_checked_at: step_fix_images HEAD-checks article images.
  Stable R2 URLs don't change, so re-checking them every run is
  pure waste (~300 HTTP calls ≈ 5-10 min per run). We skip articles
  checked in the last 24h.

Both columns are nullable with no default — existing rows get NULL,
which means "not attempted / never checked" and behaves identically
to the old code path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5e9f3a1c2d8'
down_revision: Union[str, None] = '0a7c08d01fe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'articles',
        sa.Column('llm_failed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'articles',
        sa.Column('image_checked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'stories',
        sa.Column('llm_failed_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Indexes to speed up the "skip recently failed" / "skip recently checked"
    # filters in step_bias_score, step_summarize, and step_fix_images.
    op.create_index(
        'idx_articles_llm_failed_at',
        'articles',
        ['llm_failed_at'],
        postgresql_where=sa.text('llm_failed_at IS NOT NULL'),
    )
    op.create_index(
        'idx_articles_image_checked_at',
        'articles',
        ['image_checked_at'],
        postgresql_where=sa.text('image_checked_at IS NOT NULL'),
    )
    op.create_index(
        'idx_stories_llm_failed_at',
        'stories',
        ['llm_failed_at'],
        postgresql_where=sa.text('llm_failed_at IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('idx_stories_llm_failed_at', table_name='stories')
    op.drop_index('idx_articles_image_checked_at', table_name='articles')
    op.drop_index('idx_articles_llm_failed_at', table_name='articles')
    op.drop_column('stories', 'llm_failed_at')
    op.drop_column('articles', 'image_checked_at')
    op.drop_column('articles', 'llm_failed_at')

"""add is_edited flag on stories

Revision ID: e9f7a3d5c8b1
Revises: d8e5f1a2b3c4
Create Date: 2026-04-15 00:00:00.000000

Why:
- When an admin hand-edits title_fa/title_en/state_summary_fa/diaspora_summary_fa
  /bias_explanation_fa via the dashboard editor, we flip is_edited=true so the
  maintenance pipeline's summarize + bias-scoring steps skip this story on
  subsequent runs. Otherwise the nightly pipeline would happily overwrite the
  human edit with a fresh LLM response.
- Default false preserves existing behavior for all current rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9f7a3d5c8b1'
down_revision: Union[str, None] = 'd8e5f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'stories',
        sa.Column(
            'is_edited',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    op.drop_column('stories', 'is_edited')

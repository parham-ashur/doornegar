"""add source suggestions table

Revision ID: ab8b36cf5aad
Revises: 4d99807e3652
Create Date: 2026-04-11 13:52:33.173457
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'ab8b36cf5aad'
down_revision: Union[str, None] = '4d99807e3652'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'source_suggestions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('suggestion_type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('suggested_category', sa.String(length=20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('submitter_name', sa.String(length=100), nullable=True),
        sa.Column('submitter_contact', sa.String(length=200), nullable=True),
        sa.Column('submitter_notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_suggestion_status', 'source_suggestions', ['status'])
    op.create_index('idx_suggestion_created_at', 'source_suggestions', [sa.literal_column('created_at DESC')])


def downgrade() -> None:
    op.drop_index('idx_suggestion_created_at', table_name='source_suggestions')
    op.drop_index('idx_suggestion_status', table_name='source_suggestions')
    op.drop_table('source_suggestions')

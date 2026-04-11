"""add improvement feedback table

Revision ID: 0a7c08d01fe5
Revises: ab8b36cf5aad
Create Date: 2026-04-11 14:08:13.433796
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a7c08d01fe5'
down_revision: Union[str, None] = 'ab8b36cf5aad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'improvement_feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('target_type', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.String(length=100), nullable=True),
        sa.Column('target_url', sa.Text(), nullable=True),
        sa.Column('issue_type', sa.String(length=30), nullable=False),
        sa.Column('current_value', sa.Text(), nullable=True),
        sa.Column('suggested_value', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('rater_name', sa.String(length=100), nullable=True),
        sa.Column('rater_contact', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_improvement_status', 'improvement_feedback', ['status'])
    op.create_index('idx_improvement_created_at', 'improvement_feedback', [sa.literal_column('created_at DESC')])


def downgrade() -> None:
    op.drop_index('idx_improvement_created_at', table_name='improvement_feedback')
    op.drop_index('idx_improvement_status', table_name='improvement_feedback')
    op.drop_table('improvement_feedback')

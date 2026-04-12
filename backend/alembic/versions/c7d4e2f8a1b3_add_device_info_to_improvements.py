"""add device_info to improvement_feedback

Revision ID: c7d4e2f8a1b3
Revises: b5e9f3a1c2d8
Create Date: 2026-04-12 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d4e2f8a1b3'
down_revision: Union[str, None] = 'b5e9f3a1c2d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'improvement_feedback',
        sa.Column('device_info', sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('improvement_feedback', 'device_info')

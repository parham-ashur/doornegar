"""add centroid_embedding to stories

Revision ID: d8e5f1a2b3c4
Revises: c7d4e2f8a1b3
Create Date: 2026-04-12 02:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'd8e5f1a2b3c4'
down_revision: Union[str, None] = 'c7d4e2f8a1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stories', sa.Column('centroid_embedding', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('stories', 'centroid_embedding')

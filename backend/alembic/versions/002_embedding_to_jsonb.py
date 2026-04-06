"""Change embedding column from Vector to JSONB

Revision ID: 002
Revises: 001
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the vector column if it exists, add JSONB version
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding")
    op.add_column("articles", sa.Column("embedding", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "embedding")

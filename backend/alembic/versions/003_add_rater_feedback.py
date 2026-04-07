"""Add rater feedback table

Revision ID: 003
Revises: 002
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rater_feedback",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feedback_type", sa.String(30), nullable=False, comment="article_relevance | summary_accuracy | source_categorization"),
        # Article relevance fields
        sa.Column("story_id", sa.UUID(), sa.ForeignKey("stories.id"), nullable=True),
        sa.Column("article_id", sa.UUID(), sa.ForeignKey("articles.id"), nullable=True),
        sa.Column("is_relevant", sa.Boolean(), nullable=True),
        # Summary accuracy fields
        sa.Column("summary_rating", sa.Integer(), nullable=True, comment="1-5"),
        sa.Column("summary_correction", sa.Text(), nullable=True),
        # Source categorization fields
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("suggested_alignment", sa.String(20), nullable=True, comment="state | semi_state | independent | diaspora"),
        sa.Column("suggested_factional", sa.String(20), nullable=True),
        sa.Column("categorization_note", sa.Text(), nullable=True),
        # Timestamp
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rater_feedback_user_id", "rater_feedback", ["user_id"])
    op.create_index("ix_rater_feedback_story_id", "rater_feedback", ["story_id"])
    op.create_index("ix_rater_feedback_article_id", "rater_feedback", ["article_id"])
    op.create_index("ix_rater_feedback_source_id", "rater_feedback", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_rater_feedback_source_id", table_name="rater_feedback")
    op.drop_index("ix_rater_feedback_article_id", table_name="rater_feedback")
    op.drop_index("ix_rater_feedback_story_id", table_name="rater_feedback")
    op.drop_index("ix_rater_feedback_user_id", table_name="rater_feedback")
    op.drop_table("rater_feedback")

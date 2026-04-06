"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sources
    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_fa", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=False),
        sa.Column("rss_urls", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("state_alignment", sa.String(20), nullable=False),
        sa.Column("irgc_affiliated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("production_location", sa.String(20), nullable=False),
        sa.Column("factional_alignment", sa.String(20), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="fa"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("credibility_score", sa.Float(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_fa", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_sources_slug", "sources", ["slug"])

    # Stories
    op.create_table(
        "stories",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=True),
        sa.Column("summary_fa", sa.Text(), nullable=True),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("covered_by_state", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("covered_by_diaspora", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("coverage_diversity_score", sa.Float(), nullable=True),
        sa.Column("is_blindspot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("blindspot_type", sa.String(20), nullable=True),
        sa.Column("topics", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trending_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_stories_slug", "stories", ["slug"])

    # Articles
    op.create_table(
        "articles",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("story_id", sa.UUID(), sa.ForeignKey("stories.id"), nullable=True),
        sa.Column("title_original", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("title_fa", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="fa"),
        sa.Column("categories", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("named_entities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_articles_source_id", "articles", ["source_id"])
    op.create_index("ix_articles_story_id", "articles", ["story_id"])
    op.create_index("idx_articles_published", "articles", ["published_at"])

    # Bias scores
    op.create_table(
        "bias_scores",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", sa.UUID(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("political_alignment", sa.Float(), nullable=True),
        sa.Column("pro_regime_score", sa.Float(), nullable=True),
        sa.Column("reformist_score", sa.Float(), nullable=True),
        sa.Column("opposition_score", sa.Float(), nullable=True),
        sa.Column("framing_labels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("tone_score", sa.Float(), nullable=True),
        sa.Column("emotional_language_score", sa.Float(), nullable=True),
        sa.Column("factuality_score", sa.Float(), nullable=True),
        sa.Column("source_citation_count", sa.Integer(), nullable=True),
        sa.Column("anonymous_source_count", sa.Integer(), nullable=True),
        sa.Column("uses_loaded_language", sa.Boolean(), nullable=True),
        sa.Column("scoring_method", sa.String(20), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning_en", sa.Text(), nullable=True),
        sa.Column("reasoning_fa", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_bias_article", "bias_scores", ["article_id"])

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("is_rater", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rater_level", sa.String(20), nullable=False, server_default="novice"),
        sa.Column("training_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rater_reliability_score", sa.Float(), nullable=True),
        sa.Column("total_ratings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    # Community ratings
    op.create_table(
        "community_ratings",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("article_id", sa.UUID(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("political_alignment_rating", sa.Float(), nullable=True),
        sa.Column("factuality_rating", sa.Float(), nullable=True),
        sa.Column("framing_labels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("tone_rating", sa.Float(), nullable=True),
        sa.Column("emotional_language_rating", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("was_blind", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "article_id", name="uq_user_article_rating"),
    )

    # Ingestion log
    op.create_table(
        "ingestion_log",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("articles_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("articles_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Telegram channels
    op.create_table(
        "telegram_channels",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("political_leaning", sa.String(20), nullable=True),
        sa.Column("subscriber_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="fa"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    # Telegram posts
    op.create_table(
        "telegram_posts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_id", sa.UUID(), sa.ForeignKey("telegram_channels.id"), nullable=False),
        sa.Column("story_id", sa.UUID(), sa.ForeignKey("stories.id"), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("forwards", sa.Integer(), nullable=True),
        sa.Column("reply_count", sa.Integer(), nullable=True),
        sa.Column("urls", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("framing_labels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("shares_news_link", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_commentary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),
    )

    # Social sentiment snapshots
    op.create_table(
        "social_sentiment_snapshots",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("story_id", sa.UUID(), sa.ForeignKey("stories.id"), nullable=False),
        sa.Column("total_posts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_forwards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_channels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_sentiment", sa.Float(), nullable=True),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neutral_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("framing_distribution", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("dominant_narrative", sa.Text(), nullable=True),
        sa.Column("narrative_divergence", sa.Float(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("social_sentiment_snapshots")
    op.drop_table("telegram_posts")
    op.drop_table("telegram_channels")
    op.drop_table("ingestion_log")
    op.drop_table("community_ratings")
    op.drop_table("users")
    op.drop_table("bias_scores")
    op.drop_table("articles")
    op.drop_table("stories")
    op.drop_table("sources")

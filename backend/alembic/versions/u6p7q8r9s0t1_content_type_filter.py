"""content-type filter: rss_category, content_type, Source.content_filters

Revision ID: u6p7q8r9s0t1
Revises: t5o6p7q8r9s0
Create Date: 2026-04-26 18:00:00.000000

Why:
- Sources publish a mix of original reporting, op-eds, panel discussions,
  talk-show transcripts, and aggregator pieces that re-quote other
  outlets. We only want original news to flow into NLP / clustering /
  bias scoring; the rest is noise that bloats clusters and wastes LLM
  tokens.
- This migration adds the columns the new content-type classifier needs:
  - articles.rss_category — captured from feedparser at ingest, used
    as a heuristic signal.
  - articles.content_type — the classifier verdict (news / opinion /
    discussion / aggregation / other / unclassified).
  - articles.content_type_confidence — float, audit-friendly.
  - sources.content_filters — JSONB, defaults to {"allowed": ["news"]}.
    Lets us later whitelist opinion or other types per outlet without
    schema changes.
- Existing articles are backfilled to content_type='news' so the
  pre-existing pool keeps flowing. The classifier only labels
  newly-ingested rows from now on.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "u6p7q8r9s0t1"
down_revision: Union[str, None] = "t5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS rss_category TEXT")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type VARCHAR(20)")
    op.execute(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type_confidence DOUBLE PRECISION"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_content_type "
        "ON articles(content_type) WHERE content_type IS NOT NULL"
    )

    op.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS content_filters JSONB")
    op.execute(
        "UPDATE sources SET content_filters = '{\"allowed\": [\"news\"]}'::jsonb "
        "WHERE content_filters IS NULL"
    )

    # Backfill existing articles so the new NLP gate doesn't strand them.
    # Only articles ingested before this migration; new ingests get
    # classified by the classifier step.
    op.execute(
        "UPDATE articles SET content_type = 'news', content_type_confidence = 1.0 "
        "WHERE content_type IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_content_type")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS content_type_confidence")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS content_type")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS rss_category")
    op.execute("ALTER TABLE sources DROP COLUMN IF EXISTS content_filters")

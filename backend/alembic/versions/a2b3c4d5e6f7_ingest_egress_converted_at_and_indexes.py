"""ingest egress fix — telegram_posts.converted_at sentinel + recency indexes

Revision ID: a2b3c4d5e6f7
Revises: z1u2v3w4x5y6
Create Date: 2026-06-01 06:00:00.000000

Why (2026-06-01): the maintenance `ingest` step was burning ~4.6 GB of
Neon egress PER RUN (1.2M rows scanned), measured via the per-step meter
— enough that a full run hit the 5 GB daily cap and halted before
clustering. Root cause: convert_telegram_posts_to_articles re-read every
telegram post from the last 7 days (full `text` rows) on every run, even
already-processed ones; and the aggregator URL-dedup scanned the whole
articles table (`WHERE ingested_at >= 30d`, unindexed).

This migration:
  - adds telegram_posts.converted_at so the conversion loads only
    UNPROCESSED posts (partial index serves that exact query);
  - indexes articles.ingested_at so the (now 7d) aggregator dedup is an
    index range scan, not a seq scan;
  - backfills converted_at for posts older than 1 day (prior runs already
    processed them) so the first post-deploy run doesn't reprocess the
    whole backlog. Guarded (<1d stays NULL) so fresh posts still convert.

Idempotent: the same DDL + guarded backfill run at FastAPI startup via
app/main.py self-heal, so production applies it on deploy.
"""

from alembic import op


revision = "a2b3c4d5e6f7"
down_revision = "z1u2v3w4x5y6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE telegram_posts ADD COLUMN IF NOT EXISTS converted_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_posts_unconverted "
        "ON telegram_posts(date) WHERE converted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_ingested_at ON articles(ingested_at)"
    )
    op.execute(
        "UPDATE telegram_posts SET converted_at = COALESCE(date, created_at, NOW()) "
        "WHERE converted_at IS NULL AND COALESCE(date, created_at) < NOW() - INTERVAL '1 day'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_ingested_at")
    op.execute("DROP INDEX IF EXISTS idx_telegram_posts_unconverted")
    op.execute("ALTER TABLE telegram_posts DROP COLUMN IF EXISTS converted_at")

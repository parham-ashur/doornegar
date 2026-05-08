"""pgvector embedding columns alongside JSONB (cycle-4 egress fix)

Revision ID: z1u2v3w4x5y6
Revises: y0t1u2v3w4x5
Create Date: 2026-05-08 13:00:00.000000

Why: `Article.embedding` and `Story.centroid_embedding` are JSONB arrays
of 384 floats — 3,772 B and 3,066 B per row respectively (measured via
egress audit). At ~109M tup_returned across the cron pipeline, this
JSONB encoding alone accounts for ~50% of Neon egress.

Switching to pgvector's `vector(384)` cuts each row to ~1,540 B (binary
float4×384) — ~60% byte reduction. Combined with future use of the
`<=>` SQL cosine operator, even the row COUNT can drop because
Postgres can return scalar similarity scores instead of full vectors.

Phase 1 (this migration):
- Enable extension (idempotent).
- Add `embedding_v vector(384)` to articles (alongside existing JSONB).
- Add `centroid_embedding_v vector(384)` to stories (alongside).
- Backfill is in a separate command path (script + on-write dual-mode).

Phase 2 (later):
- Switch readers to `_v` columns.
- Drop original JSONB columns once stable.

Idempotent: matches the self-heal DDL block in app/main.py for fresh
deploys.
"""

from alembic import op


revision = "z1u2v3w4x5y6"
down_revision = "y0t1u2v3w4x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Neon supports pgvector since 2023; CREATE EXTENSION is a no-op
    # if already installed.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_v vector(384)"
    )
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS centroid_embedding_v vector(384)"
    )
    # Index for future cosine-similarity SQL pushdown via the
    # `<=>` operator. ivfflat is the canonical choice for ≤1M rows;
    # tunable `lists` approximates √rows ≈ 180 for our 32k articles.
    # The index is built lazily on first query, so adding it here
    # doesn't block the migration.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_embedding_v_cosine "
        "ON articles USING ivfflat (embedding_v vector_cosine_ops) "
        "WITH (lists = 100) "
        "WHERE embedding_v IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_centroid_v_cosine "
        "ON stories USING ivfflat (centroid_embedding_v vector_cosine_ops) "
        "WITH (lists = 50) "
        "WHERE centroid_embedding_v IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_embedding_v_cosine")
    op.execute("DROP INDEX IF EXISTS idx_stories_centroid_v_cosine")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding_v")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS centroid_embedding_v")
    # Don't DROP EXTENSION — other tables may use it.

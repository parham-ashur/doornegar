"""sources.name_fr column for EN+FR rollout Phase 0d

Revision ID: x9s0t1u2v3w4
Revises: w8r9s0t1u2v3
Create Date: 2026-05-06 22:30:00.000000

Why: completes the source-name glossary for the multi-locale rollout.
sources.name_en and sources.name_fa already exist; this adds the
French equivalent (nullable). Population comes in Phase 1 from the
canonical glossary in memory `project_en_fr_rollout.md`. Until
populated, voice prompts fall back to name_en plus an inline lookup
table for the well-known Persian outlet names.

Idempotent: same DDL is applied at FastAPI startup via the self-heal
block in app/main.py.
"""

from alembic import op


revision = "x9s0t1u2v3w4"
down_revision = "w8r9s0t1u2v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS name_fr VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE sources DROP COLUMN IF EXISTS name_fr")

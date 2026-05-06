"""multi-locale translations JSONB columns + partial indexes

Revision ID: w8r9s0t1u2v3
Revises: v7q8r9s0t1u2
Create Date: 2026-05-06 22:00:00.000000

Why (Parham 2026-05-06, EN+FR rollout Phase 0):
- Adds `stories.translations` JSONB blob holding per-locale (en, fr) slots
  for title, summary, narratives, doornama, bias_explanation, plus
  metadata (translated_at, prompt_version, is_edited, edit_anchor).
- Adds `articles.title_translations` JSONB for per-locale article-title
  translations populated by the utility-tier batch translator.
- Two partial indexes on the JSONB title path so step_translate_homepage_visible
  can find untranslated homepage-eligible stories without a sequential
  scan over the whole stories table.

Idempotent: same DDL is applied at FastAPI startup via the self-heal
block in app/main.py. This migration is for traceability + fresh-DB
bootstrap. Production already has these objects from the self-heal path
on the first deploy after this commit.

Schema documented in memory `project_en_fr_rollout.md`.
"""

from alembic import op


revision = "w8r9s0t1u2v3"
down_revision = "v7q8r9s0t1u2"
branch_labels = None
depends_on = None


_DDL = [
    "ALTER TABLE stories ADD COLUMN IF NOT EXISTS translations JSONB",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS title_translations JSONB",
    "CREATE INDEX IF NOT EXISTS idx_stories_en_missing ON stories ((translations->'en'->>'title')) WHERE translations->'en'->>'title' IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_stories_fr_missing ON stories ((translations->'fr'->>'title')) WHERE translations->'fr'->>'title' IS NULL",
]


def upgrade() -> None:
    for stmt in _DDL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stories_fr_missing")
    op.execute("DROP INDEX IF EXISTS idx_stories_en_missing")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS title_translations")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS translations")

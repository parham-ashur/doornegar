"""add worldview_digests table

Revision ID: p1k2l3m4n5o6
Revises: o0j1k2l3m4n5
Create Date: 2026-04-24 11:30:00.000000

Why:
- Weekly worldview synthesis, one row per (bundle, window). Bundles map
  to the existing 4-subgroup taxonomy (principlist, reformist,
  moderate_diaspora, radical_diaspora). Not "what readers of group X
  believe" — what the OUTLETS in that group told their readers over
  the window. Keeps the editorial "outlets said, not readers believe"
  caveat load-bearing by design: the table columns are outlet-level,
  not reader-level.
- status field lets the pipeline record insufficient-signal weeks
  (<20 articles, <3 sources, or <75% bias-analysis coverage) without
  writing a misleading synthesis.
- synthesis_fa holds the structured JSON the LLM returns (core_beliefs,
  emphasized, absent, tone_profile, predictions_primed). evidence_fa
  keeps the citation chain so any belief on the card can be clicked
  back to its source articles.
- Idempotent IF NOT EXISTS pattern so app/main.py startup self-heal
  stays safe on a fresh deploy.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "p1k2l3m4n5o6"
down_revision: Union[str, None] = "o0j1k2l3m4n5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS worldview_digests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bundle VARCHAR(24) NOT NULL,
            window_start DATE NOT NULL,
            window_end DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'ok',
            synthesis_fa JSONB,
            evidence_fa JSONB,
            article_count INTEGER NOT NULL DEFAULT 0,
            source_count INTEGER NOT NULL DEFAULT 0,
            coverage_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
            model_used VARCHAR(80),
            token_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_worldview_bundle_window UNIQUE (bundle, window_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_worldview_window "
        "ON worldview_digests(window_start DESC, bundle)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_worldview_bundle_recent "
        "ON worldview_digests(bundle, generated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_worldview_bundle_recent")
    op.execute("DROP INDEX IF EXISTS idx_worldview_window")
    op.execute("DROP TABLE IF EXISTS worldview_digests")

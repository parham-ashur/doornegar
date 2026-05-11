"""stories.homepage_aggregates — denormalized per-story image + percentages blob

Revision ID: z1u2v3w4x5y6
Revises: y0t1u2v3w4x5
Create Date: 2026-05-10 21:00:00.000000

Why: Phase G.3.2 (Parham 2026-05-10). The /trending and /blindspots
endpoints today eager-load every Story's articles via
selectinload(Story.articles) only to compute coverage percentages and
pick a cover image — both deterministic per-story aggregates that
shift only on the 6h cron cadence. Storing the aggregates inline on
Story unlocks dropping the article load entirely (Phase 2 of G.3.2,
ships in a follow-up after first cron populates the blob).

Shape:
    {"image_url": str|null, "has_real_image": bool,
     "state_pct": int, "diaspora_pct": int, "independent_pct": int,
     "narrative_groups": {"principlist": int, "reformist": int,
                          "moderate_diaspora": int, "radical_diaspora": int},
     "inside_border_pct": int, "outside_border_pct": int,
     "computed_at": ISO8601}

Idempotent: same DDL runs at FastAPI startup via app/main.py self-heal.
"""

from alembic import op


revision = "z1u2v3w4x5y6"
down_revision = "y0t1u2v3w4x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS "
        "homepage_aggregates JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE stories DROP COLUMN IF EXISTS homepage_aggregates"
    )

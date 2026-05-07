"""articles.last_r2_migration_attempt_at — sentinel for R2 image migration retries

Revision ID: y0t1u2v3w4x5
Revises: x9s0t1u2v3w4
Create Date: 2026-05-07 20:30:00.000000

Why: step_migrate_images_to_r2 (auto_maintenance.py) downloads source-CDN
images and re-hosts them on R2. Pre-this-migration the retry gate was a
naked `image_url NOT LIKE r2_prefix`, which means a chronically broken
upstream URL got re-attempted on every cron forever (and burned the 150-
slot batch on doomed work).

Adding this timestamp lets the gate become:
  WHERE image_url NOT LIKE r2_prefix
    AND (last_r2_migration_attempt_at IS NULL
         OR last_r2_migration_attempt_at < NOW() - INTERVAL '24 hours')

Stamped on every attempt (success + failure) so chronic failures back
off to one retry per day instead of one per cron (3×/day).

Idempotent: same DDL runs at FastAPI startup via app/main.py self-heal.
Cycle-1 audit Island 8 deferred this; ships in cycle-2 (2026-05-07).
"""

from alembic import op


revision = "y0t1u2v3w4x5"
down_revision = "x9s0t1u2v3w4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS "
        "last_r2_migration_attempt_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE articles DROP COLUMN IF EXISTS last_r2_migration_attempt_at"
    )

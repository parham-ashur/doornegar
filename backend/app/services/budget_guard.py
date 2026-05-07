"""Budget kill-switch for the maintenance pipeline.

A strict-mode rule: if the project's month-to-date spend reaches a
threshold of the $30/mo hard cap, the cron pipeline aborts before
running any expensive step. This prevents an unanticipated cost
spike (Neon egress, OpenAI runaway, Vercel CPU) from draining the
entire budget in days and ending the project.

The user (Parham 2026-05-07) explicitly chose:
> "There should be a strict rule that prevents [unanticipated costs]
> from happening, even if it means that website is not updating.
> Unanticipated costs are dangerous for this project and all the
> positive impact it wants to give to humanity."

Source-of-truth signals:
- LLM cost MTD from llm_usage_logs.total_cost (covers OpenAI + Anthropic)
- pg_stat_database egress proxy (blks_read × 8KB)
- Manual override flag in `budget_override` table (operator override)

When any signal trips, `should_halt_for_budget()` returns the
reason. Caller (run_maintenance) writes a maintenance_log row
showing the abort and exits early without touching any expensive
step.

Manual override / reset:
- POST /admin/budget/override?action=lock  → halt regardless
- POST /admin/budget/override?action=clear → permit one cron run
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text as _sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# $30/mo hard cap from project_cost_budget memory.
MONTHLY_BUDGET_USD = 30.0

# Halt the cron when LLM month-to-date crosses this fraction.
# 0.80 leaves $6 of headroom for the rest of the month, which
# typically covers 5-7 days of normal pipeline activity.
HALT_FRACTION_LLM = 0.80

# Hard halt regardless. Even if LLM is fine, this catches Neon
# egress spikes (the 2026-05-07 incident: $18.15 in 7 days from
# Neon data transfer alone, projecting to $77/mo).
HALT_HARD_USD = MONTHLY_BUDGET_USD * 0.85  # $25.50

# Cron RUNS the cheap-only steps even when budget halts. The two
# tiers below let us continue ingest+classify (which keep the
# pipeline data coherent) while shutting off LLM-heavy work.
CHEAP_STEPS = {
    "ingest", "prune_noise", "recount", "classify_content_type",
    "process", "backfill_farsi_titles", "cluster", "centroids",
    "recluster_orphans", "telegram_link", "merge_similar",
    "recalc_trending_pre_summarize", "recalc_trending",
    "dedup_articles", "fixes", "flag_unrelated", "image_relevance",
    "rater_feedback", "summary_corrections", "niloofar_feedback_audit",
    "age_out_stale_feedback", "source_trust", "feedback_health",
    "telegram_health", "visual", "uptime", "disk", "cost_tracking",
    "backup", "retention_audit", "archive_stale", "prune_stagnant",
    "demote_umbrellas", "source_health", "story_quality",
    "fix_images", "diaspora_ogimages", "migrate_images_r2",
    "niloofar_image_rescue", "snapshot_analyses", "audit_clusters",
    "detect_hourly_updates", "backfill_analyst_counts",
    "telegram_session", "telegram_health",
}

# Steps that ALWAYS get skipped when the budget guard fires —
# these are the LLM/egress-heavy ones. Skipping them lets the
# pipeline still keep ingest + classification fresh while saving
# the bulk of the spend.
HALT_SKIP_STEPS = {
    "summarize", "summarize_newly_visible", "bias_score",
    "editorial", "niloofar_polish_telegram", "detect_silences",
    "detect_coordination", "telegram_analysis", "verify_predictions",
    "analyst_takes", "quality_postprocess",
    "weekly_digest", "worldview_digests",
    "translate_homepage_visible",  # the new step
}


async def get_llm_cost_mtd(db: AsyncSession) -> float:
    """Return month-to-date LLM cost in USD."""
    cost = float(
        (
            await db.execute(
                _sa_text(
                    "SELECT COALESCE(SUM(total_cost), 0) "
                    "FROM llm_usage_logs "
                    "WHERE timestamp >= date_trunc('month', NOW())"
                )
            )
        ).scalar()
        or 0.0
    )
    return cost


async def get_manual_override(db: AsyncSession) -> Optional[str]:
    """Returns the manual override action ('lock'|'clear'|None).

    Reads from a single-row table `budget_override`. Schema:
        id SMALLINT PRIMARY KEY DEFAULT 1
        action VARCHAR(10)  -- 'lock' or 'clear' or NULL
        set_at TIMESTAMPTZ
        reason TEXT

    'lock' wins over LLM-cost permits; 'clear' wins over
    LLM-cost halts (one-shot — auto-resets after the next cron
    completes).
    """
    try:
        row = (
            await db.execute(
                _sa_text(
                    "SELECT action FROM budget_override WHERE id = 1"
                )
            )
        ).first()
        return row.action if row else None
    except Exception:
        # Table doesn't exist yet on first deploy — that's fine,
        # falls through to the cost check.
        return None


async def should_halt_for_budget(db: AsyncSession) -> tuple[bool, str, dict]:
    """Decide whether to halt the cron.

    Returns (halt: bool, reason: str, signals: dict).
    """
    llm_mtd = await get_llm_cost_mtd(db)
    override = await get_manual_override(db)

    signals = {
        "llm_cost_mtd_usd": round(llm_mtd, 4),
        "monthly_budget_usd": MONTHLY_BUDGET_USD,
        "halt_fraction_llm": HALT_FRACTION_LLM,
        "halt_hard_usd": HALT_HARD_USD,
        "manual_override": override,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if override == "lock":
        return True, "manual_lock", signals
    if override == "clear":
        # One-shot pass — clear the override after this read so the
        # next cron is back under normal rules.
        try:
            await db.execute(
                _sa_text(
                    "UPDATE budget_override SET action = NULL, "
                    "set_at = NOW() WHERE id = 1"
                )
            )
            await db.commit()
        except Exception:
            logger.exception("Failed to clear budget_override")
        return False, "manual_clear_one_shot", signals

    if llm_mtd >= HALT_HARD_USD:
        return True, f"llm_mtd_{llm_mtd:.2f}_over_hard_cap_{HALT_HARD_USD}", signals

    if llm_mtd >= MONTHLY_BUDGET_USD * HALT_FRACTION_LLM:
        return (
            True,
            f"llm_mtd_{llm_mtd:.2f}_over_{HALT_FRACTION_LLM:.0%}_of_{MONTHLY_BUDGET_USD}",
            signals,
        )

    return False, "ok", signals


async def ensure_budget_override_table(db: AsyncSession) -> None:
    """Idempotent DDL for the override table. Called from
    self-heal at app startup so the lock-clear admin endpoint
    works on a fresh DB.
    """
    try:
        await db.execute(
            _sa_text(
                """
                CREATE TABLE IF NOT EXISTS budget_override (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    action VARCHAR(10),
                    set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT,
                    CHECK (id = 1)
                )
                """
            )
        )
        await db.execute(
            _sa_text(
                "INSERT INTO budget_override (id, action) VALUES (1, NULL) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to ensure budget_override table")

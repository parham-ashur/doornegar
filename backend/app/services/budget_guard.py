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
    "rater_feedback",
    "age_out_stale_feedback", "source_trust", "feedback_health",
    "telegram_health", "visual", "uptime", "disk", "cost_tracking",
    "backup", "retention_audit", "archive_stale", "prune_stagnant",
    "demote_umbrellas", "source_health", "story_quality",
    "fix_images", "diaspora_ogimages", "migrate_images_r2",
    "niloofar_image_rescue", "snapshot_analyses", "audit_clusters",
    "detect_hourly_updates", "backfill_analyst_counts",
    "telegram_session",
}

# Steps that ALWAYS get skipped when the budget guard fires —
# these are the LLM/egress-heavy ones. Skipping them lets the
# pipeline still keep ingest + classification fresh while saving
# the bulk of the spend.
#
# Cycle-2 audit (2026-05-07): moved `summary_corrections` and
# `niloofar_feedback_audit` from CHEAP_STEPS to HALT_SKIP_STEPS.
# Both call OpenAI/Anthropic respectively; capping them at 20
# stories/run × ~$0.005 still costs ~$0.30/day under halt — small
# but contradicts the kill-switch invariant ("website goes stale
# before project dies"). When the cap arms, ALL LLM spend halts.
HALT_SKIP_STEPS = {
    "summarize", "summarize_newly_visible", "bias_score",
    "editorial", "niloofar_polish_telegram", "detect_silences",
    "detect_coordination", "telegram_analysis", "verify_predictions",
    "analyst_takes", "quality_postprocess",
    "weekly_digest", "worldview_digests",
    "translate_homepage_visible",  # the new step
    "summary_corrections", "niloofar_feedback_audit",
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


async def get_neon_egress_estimate_mtd(db: AsyncSession) -> tuple[float, float]:
    """Return (estimated_egress_gb_mtd, estimated_cost_usd_mtd).

    Uses pg_stat_database.tup_returned × average row width as a proxy
    for Neon's billed data transfer. This is approximate — Neon's
    official metric is bytes-on-the-wire which includes protocol
    overhead — but it's the best signal available from inside the DB.

    Calibration anchor: 2026-05-07 incident showed 281 GB egress in
    7 days at $18.15. That's $0.065/GB. Neon's documented data
    transfer price is around that range.
    """
    GB = 1024 * 1024 * 1024
    BYTES_PER_GB_USD = 0.065

    try:
        row = (await db.execute(_sa_text(
            """
            SELECT
              tup_returned,
              EXTRACT(EPOCH FROM (NOW() - GREATEST(
                stats_reset, date_trunc('month', NOW())
              ))) AS seconds_since_anchor
            FROM pg_stat_database
            WHERE datname = current_database()
            """
        ))).mappings().one_or_none()
        if not row:
            return 0.0, 0.0

        # tup_returned counts rows scanned (including index scans that
        # don't touch heap). Each row averages roughly the table heap
        # size / row count. Conservative: assume average row weight of
        # 4 KB (between articles ~10 KB and stories ~22 KB and
        # llm_usage_logs ~360 B and bias_scores ~1 KB). Calibration
        # via the 2026-05-07 incident confirms this is in the right
        # order of magnitude.
        AVG_ROW_BYTES = 4 * 1024

        tup_returned_mtd = int(row["tup_returned"] or 0)
        bytes_estimate = tup_returned_mtd * AVG_ROW_BYTES
        gb_estimate = bytes_estimate / GB
        cost_estimate = gb_estimate * BYTES_PER_GB_USD
        return gb_estimate, cost_estimate
    except Exception:
        logger.exception("get_neon_egress_estimate_mtd failed")
        return 0.0, 0.0


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
    egress_gb, egress_cost = await get_neon_egress_estimate_mtd(db)
    override = await get_manual_override(db)
    combined_mtd = llm_mtd + egress_cost

    signals = {
        "llm_cost_mtd_usd": round(llm_mtd, 4),
        "neon_egress_estimate_gb_mtd": round(egress_gb, 2),
        "neon_cost_estimate_usd_mtd": round(egress_cost, 4),
        "combined_cost_estimate_usd_mtd": round(combined_mtd, 4),
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

    # Neon egress alone can blow the budget without LLM spend rising
    # (the 2026-05-07 incident: $18.15 of pure data transfer in 7
    # days). The combined check catches both.
    if combined_mtd >= HALT_HARD_USD:
        return (
            True,
            f"combined_mtd_{combined_mtd:.2f}_over_hard_cap_{HALT_HARD_USD}",
            signals,
        )

    # (Cycle-1 audit Island 12: removed unreachable LLM-only halt branch
    # here. The combined_mtd check above already covers this case since
    # combined_mtd >= llm_mtd by definition.)

    if combined_mtd >= MONTHLY_BUDGET_USD * HALT_FRACTION_LLM:
        return (
            True,
            f"combined_mtd_{combined_mtd:.2f}_over_{HALT_FRACTION_LLM:.0%}_of_{MONTHLY_BUDGET_USD}",
            signals,
        )

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

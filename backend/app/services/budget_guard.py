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

# Parham 2026-05-09: Neon free tier allows 100 GB/month outbound
# data transfer. 100 / 30 = ~3.33 GB/day. We cap at 3.0 GB/day to
# leave 10% headroom for unexpected spikes. When today's egress
# (estimated from pg_stat_database.tup_returned delta since
# start-of-day snapshot) crosses this threshold, the entire cron
# pipeline halts — same semantics as a manual_lock. This is a
# hard rule that survived the 2026-05-09 30 GB egress incident
# (caused by HALT_SKIP_STEPS only covering LLM-heavy steps; the
# ~41 non-LLM steps still ran on every cron fire under the lock).
DAILY_EGRESS_CAP_GB = 2.0
# Same calibration anchor as MTD: 4 KB average row weight, mapping
# tup_returned (rows) to bytes-on-the-wire estimate. Estimate runs
# ~30-50% high vs Neon's actual billing — that's intentional. The
# cap at 2 GB ESTIMATE corresponds to ~1.3 GB ACTUAL billing, well
# under the 3.33 GB/day allotment (40% of the free tier per day).
#
# Phase G.4 (Parham 2026-05-12): lowered from 3.0 → 2.0 after the
# Phase G structural cuts + clean slate + dashboard cache fix.
# Post-Phase G measured baseline runs well under 1.5 GB/day; a 2.0
# cap with 1.0 warning gives early signal at 50% and hard halt at
# the new survival floor. To raise this back up, you need explicit
# Parham acknowledgement (see strict-rule "3gb-daily-egress-cap"
# in CLAUDE.md, which now reads "2gb-daily-egress-cap").
DAILY_EGRESS_AVG_ROW_BYTES = 4 * 1024

# Warning threshold (Phase G.4 — 50% of cap). When today's egress
# crosses this, surface a warning in /admin/budget/status without
# halting. Lets the operator see the trajectory before the cap fires.
DAILY_EGRESS_WARN_GB = 1.0

# Cron RUNS the cheap-only steps even when budget halts. The two
# tiers below let us continue ingest+classify (which keep the
# pipeline data coherent) while shutting off LLM-heavy work.
CHEAP_STEPS = {
    "ingest", "prune_noise", "recount", "recount_after_dedup",
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
    # Phase G.3.2 (Parham 2026-05-10): denormalize step. Pure DB
    # read+write — must keep running during soft-halt so the homepage
    # stays fresh while LLM steps are paused.
    "homepage_aggregates",
    # Phase G follow-up (Parham 2026-05-12): retention deletes. Pure
    # DB operation, no LLM. Keep running during soft-halt so the
    # database stays lean even while LLM steps are paused.
    "delete_aged",
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
    # Cycle-4 (2026-05-08): classify_content_type calls
    # gpt-4.1-nano on ambiguous articles. Heuristics catch most,
    # but stress-mode flood proportion stays the same → 2-5×
    # LLM calls vs steady-state. Was leaking through CHEAP_STEPS.
    "classify_content_type",
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


async def get_daily_egress_estimate(db: AsyncSession) -> tuple[float, int]:
    """Return (estimated_egress_gb_today, current_tup_returned).

    Computes today's tup_returned delta against the start-of-day
    snapshot persisted in egress_daily_snapshot. If no snapshot exists
    yet for today (first call after UTC midnight), creates one and
    returns 0.0 — the new day starts at zero.

    Idempotent and self-healing: works on a fresh DB once
    ensure_budget_override_table has run.

    Parham 2026-05-09: implements the 3 GB/day cap.
    """
    GB = 1024 * 1024 * 1024

    try:
        row = (await db.execute(_sa_text(
            "SELECT tup_returned FROM pg_stat_database "
            "WHERE datname = current_database()"
        ))).first()
        current_tup = int(row.tup_returned or 0) if row else 0
    except Exception:
        logger.exception("get_daily_egress_estimate: pg_stat_database read failed")
        return 0.0, 0

    today_utc = datetime.now(timezone.utc).date()

    try:
        snap = (await db.execute(
            _sa_text(
                "SELECT tup_returned_start FROM egress_daily_snapshot "
                "WHERE day = :d"
            ),
            {"d": today_utc},
        )).first()

        if snap is None:
            # First call today — capture the snapshot. Today's egress
            # starts at 0. Subsequent calls today compute delta against
            # this anchor.
            await db.execute(
                _sa_text(
                    "INSERT INTO egress_daily_snapshot "
                    "(day, tup_returned_start, set_at) "
                    "VALUES (:d, :t, NOW()) "
                    "ON CONFLICT (day) DO NOTHING"
                ),
                {"d": today_utc, "t": current_tup},
            )
            await db.commit()
            return 0.0, current_tup

        snap_tup = int(snap.tup_returned_start or 0)
        delta_rows = max(0, current_tup - snap_tup)
        delta_bytes = delta_rows * DAILY_EGRESS_AVG_ROW_BYTES
        return delta_bytes / GB, current_tup
    except Exception:
        logger.exception("get_daily_egress_estimate: snapshot read failed")
        return 0.0, current_tup


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


async def should_halt_for_budget(
    db: AsyncSession, *, consume_override: bool = True
) -> tuple[bool, str, dict]:
    """Decide whether to halt the cron.

    Returns (halt: bool, reason: str, signals: dict).

    `consume_override`: when True (cron pre-flight default), a `clear`
    override is reset to NULL after this call — that's what makes
    `clear` a one-shot. When False (read-only callers like
    /admin/budget/status), the override is preserved so dashboard
    polling doesn't accidentally consume the operator's one-shot.

    Cycle-3 fix (2026-05-08): pre-this-fix every call to
    should_halt_for_budget consumed the override, including reads from
    the dashboard's /budget/status polling. This caused the 2026-05-08
    morning cron to halt despite the operator clearing the override
    7h before — some intermediate /budget/status call ate it.
    """
    llm_mtd = await get_llm_cost_mtd(db)
    egress_gb, egress_cost = await get_neon_egress_estimate_mtd(db)
    daily_egress_gb, _current_tup = await get_daily_egress_estimate(db)
    override = await get_manual_override(db)
    combined_mtd = llm_mtd + egress_cost

    signals = {
        "llm_cost_mtd_usd": round(llm_mtd, 4),
        "neon_egress_estimate_gb_mtd": round(egress_gb, 2),
        "neon_cost_estimate_usd_mtd": round(egress_cost, 4),
        "combined_cost_estimate_usd_mtd": round(combined_mtd, 4),
        "neon_egress_estimate_gb_today": round(daily_egress_gb, 3),
        "daily_egress_cap_gb": DAILY_EGRESS_CAP_GB,
        "daily_egress_warn_gb": DAILY_EGRESS_WARN_GB,
        "daily_egress_warning_active": daily_egress_gb >= DAILY_EGRESS_WARN_GB,
        "monthly_budget_usd": MONTHLY_BUDGET_USD,
        "halt_fraction_llm": HALT_FRACTION_LLM,
        "halt_hard_usd": HALT_HARD_USD,
        "manual_override": override,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if override == "lock":
        return True, "manual_lock", signals

    # Parham 2026-05-09: 3 GB/day cap. 100 GB Neon free tier / 30 days
    # = 3.33 GB/day; cap at 3.0 leaves 10% headroom. Treated like
    # manual_lock by the cron — entire pipeline halts. Resets at UTC
    # midnight via natural day-rollover. Checked BEFORE manual_clear
    # so a one-shot clear cannot bypass the daily cap (the cap is
    # the survival floor; clear is for unblocking specific runs
    # within budget).
    if daily_egress_gb >= DAILY_EGRESS_CAP_GB:
        return (
            True,
            f"daily_egress_cap_{daily_egress_gb:.2f}gb_over_{DAILY_EGRESS_CAP_GB}gb",
            signals,
        )

    if override == "clear":
        # One-shot pass. Only consume the flag when the cron is
        # actually pre-flighting; read-only callers leave it in place.
        if consume_override:
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


async def enforce_budget_or_403_dep(db: AsyncSession) -> None:
    """Inner check: raise HTTPException(403) when budget halts.

    Split out so non-FastAPI callers (background tasks, manage.py)
    can reuse the same logic without dragging in HTTP dependencies.
    """
    from fastapi import HTTPException

    halt, reason, signals = await should_halt_for_budget(
        db, consume_override=False
    )
    if halt:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "budget_halt",
                "reason": reason,
                "signals": signals,
                "hint": (
                    "Cron + admin LLM endpoints are halted. Clear "
                    "with POST /admin/budget/override?action=clear "
                    "(one-shot) or wait for next billing month."
                ),
            },
        )


async def ensure_budget_override_table(db: AsyncSession) -> None:
    """Idempotent DDL for the override + egress_daily_snapshot tables.
    Called from self-heal at app startup so the lock-clear admin
    endpoint and the 3 GB/day cap both work on a fresh DB.
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
        # Parham 2026-05-09: 3 GB/day cap snapshot table. One row per
        # UTC day. The first call to get_daily_egress_estimate after
        # midnight inserts the start-of-day tup_returned anchor; later
        # calls compute delta against it. Old rows are kept for audit
        # — small table (1 row/day = 365 rows/year × ~50 bytes ≈ 18 KB).
        await db.execute(
            _sa_text(
                """
                CREATE TABLE IF NOT EXISTS egress_daily_snapshot (
                    day DATE PRIMARY KEY,
                    tup_returned_start BIGINT NOT NULL,
                    set_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to ensure budget_override / egress_daily_snapshot tables")

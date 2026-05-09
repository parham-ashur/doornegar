"""Celery tasks for the NLP pipeline: processing, clustering, and bias scoring."""

import asyncio
import logging

from app.database import async_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _budget_halt_if_active() -> tuple[bool, str | None]:
    """Cycle-5 Phase E (2026-05-09): all worker tasks defensively check
    the budget guard at fire-time. The `manual_lock` was meant to halt
    LLM/egress-heavy work during cost emergencies, but it only fired
    from auto_maintenance.run_maintenance pre-flight. Any Celery task
    enqueued by beat or by application code routed around it.

    Returns (halt, reason). If halt=True the task should return early.
    """
    try:
        from app.services.budget_guard import should_halt_for_budget

        async with async_session() as db:
            halt, reason, _signals = await should_halt_for_budget(
                db, consume_override=False
            )
            return halt, reason
    except Exception:
        logger.exception("budget_halt_check failed; defaulting to halt")
        return True, "budget_check_error"


# NOTE: dormant in the current Railway deployment (auto_maintenance.py
# runs the pipeline). See ingest_task.py for the full explanation.
#
# Cycle-5 Phase E (2026-05-09): even when "dormant", these tasks listen
# on Redis. If anything (a stray beat, application code, manual enqueue)
# fires them, they MUST respect the budget guard. The 2026-05-09 30 GB
# Neon egress jump exposed this gap — the lock was on the cron, not on
# the workers.


@celery_app.task(name="app.workers.nlp_task.process_nlp_batch_task", bind=True)
def process_nlp_batch_task(self):
    """Process unprocessed articles through the NLP pipeline.

    Runs: normalization, keyword extraction, embedding generation, translation.
    """
    halt, reason = run_async(_budget_halt_if_active())
    if halt:
        logger.warning(f"process_nlp_batch_task halted by budget: {reason}")
        return {"skipped": True, "reason": reason}
    logger.info("Starting NLP batch processing...")

    async def _run():
        from app.services.nlp_pipeline import process_unprocessed_articles

        async with async_session() as db:
            return await process_unprocessed_articles(db)

    stats = run_async(_run())
    logger.info(f"NLP processing complete: {stats}")
    return stats


@celery_app.task(name="app.workers.nlp_task.cluster_stories_task", bind=True)
def cluster_stories_task(self):
    """Cluster articles into stories based on embedding similarity."""
    halt, reason = run_async(_budget_halt_if_active())
    if halt:
        logger.warning(f"cluster_stories_task halted by budget: {reason}")
        return {"skipped": True, "reason": reason}
    logger.info("Starting story clustering...")

    async def _run():
        from app.services.clustering import cluster_articles

        async with async_session() as db:
            return await cluster_articles(db)

    stats = run_async(_run())
    logger.info(f"Clustering complete: {stats}")
    return stats


@celery_app.task(name="app.workers.nlp_task.score_bias_batch_task", bind=True)
def score_bias_batch_task(self):
    """Score unscored articles for bias using LLM analysis.

    Homepage-scoped (Parham 2026-05-03): if this task ever fires from a
    Celery beat schedule we don't currently have, it MUST stay within
    the $30/mo budget by only scoring homepage-visible stories. The
    April 2026 overage was likely caused by an unscoped invocation of
    this exact codepath. Pass `homepage_only_top_n=20` so the gate
    behaves identically to the maintenance cron's `step_bias_score`.
    """
    halt, reason = run_async(_budget_halt_if_active())
    if halt:
        logger.warning(f"score_bias_batch_task halted by budget: {reason}")
        return {"skipped": True, "reason": reason}
    logger.info("Starting bias scoring batch (homepage-scoped)...")

    async def _run():
        from app.services.bias_scoring import score_unscored_articles

        async with async_session() as db:
            return await score_unscored_articles(db, homepage_only_top_n=20)

    stats = run_async(_run())
    logger.info(f"Bias scoring complete: {stats}")
    return stats

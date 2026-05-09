"""Celery task for RSS feed ingestion."""

import asyncio
import logging

from app.database import async_session
from app.services.ingestion import ingest_all_sources
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# NOTE: these Celery tasks are DORMANT in the current Railway deployment
# (only `web` + a scheduled `auto_maintenance.py` cron run). The safety
# nets that used to live here (time_limit, single_flight lock) were moved
# to auto_maintenance.py where they actually protect the pipeline.
# Re-activate these decorators if you add `worker` + `beat` services.


@celery_app.task(name="app.workers.ingest_task.ingest_all_feeds_task", bind=True)
def ingest_all_feeds_task(self):
    """Periodic task to ingest RSS feeds from all active sources.

    Cycle-5 Phase E (2026-05-09): defensive budget guard. Even though
    this task is documented as dormant, the worker process listens on
    Redis and would execute any enqueue. The lock on the FULL_PIPELINE
    cron does not protect this codepath.
    """
    from app.workers.nlp_task import _budget_halt_if_active
    halt, reason = run_async(_budget_halt_if_active())
    if halt:
        logger.warning(f"ingest_all_feeds_task halted by budget: {reason}")
        return {"skipped": True, "reason": reason}
    logger.info("Starting scheduled feed ingestion...")

    async def _run():
        async with async_session() as db:
            try:
                stats = await ingest_all_sources(db)
                return stats
            except Exception as e:
                logger.exception("Feed ingestion failed")
                raise

    stats = run_async(_run())
    logger.info(f"Feed ingestion complete: {stats}")
    return stats

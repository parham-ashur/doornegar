"""Celery task for RSS feed ingestion."""

import asyncio
import logging

from app.database import async_session
from app.services.ingestion import ingest_all_sources
from app.workers.celery_app import celery_app
from app.workers.task_lock import single_flight

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.ingest_task.ingest_all_feeds_task",
    bind=True,
    time_limit=900,        # 15 min hard kill
    soft_time_limit=870,   # graceful at 14:30
)
@single_flight("ingest_all_feeds", timeout=960)
def ingest_all_feeds_task(self):
    """Periodic task to ingest RSS feeds from all active sources."""
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

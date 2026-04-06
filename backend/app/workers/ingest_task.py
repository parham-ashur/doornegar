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


@celery_app.task(name="app.workers.ingest_task.ingest_all_feeds_task", bind=True)
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

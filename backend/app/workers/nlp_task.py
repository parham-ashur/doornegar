"""Celery tasks for the NLP pipeline: processing, clustering, and bias scoring."""

import asyncio
import logging

from app.database import async_session
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
    name="app.workers.nlp_task.process_nlp_batch_task",
    bind=True,
    time_limit=1200,       # 20 min (embedding model cold start + batch)
    soft_time_limit=1170,
)
@single_flight("process_nlp_batch", timeout=1260)
def process_nlp_batch_task(self):
    """Process unprocessed articles through the NLP pipeline.

    Runs: normalization, keyword extraction, embedding generation, translation.
    """
    logger.info("Starting NLP batch processing...")

    async def _run():
        from app.services.nlp_pipeline import process_unprocessed_articles

        async with async_session() as db:
            return await process_unprocessed_articles(db)

    stats = run_async(_run())
    logger.info(f"NLP processing complete: {stats}")
    return stats


@celery_app.task(
    name="app.workers.nlp_task.cluster_stories_task",
    bind=True,
    time_limit=900,        # 15 min (LLM clustering)
    soft_time_limit=870,
)
@single_flight("cluster_stories", timeout=960)
def cluster_stories_task(self):
    """Cluster articles into stories based on embedding similarity."""
    logger.info("Starting story clustering...")

    async def _run():
        from app.services.clustering import cluster_articles

        async with async_session() as db:
            return await cluster_articles(db)

    stats = run_async(_run())
    logger.info(f"Clustering complete: {stats}")
    return stats


@celery_app.task(
    name="app.workers.nlp_task.score_bias_batch_task",
    bind=True,
    time_limit=1800,       # 30 min (per-article LLM calls)
    soft_time_limit=1770,
)
@single_flight("score_bias_batch", timeout=1860)
def score_bias_batch_task(self):
    """Score unscored articles for bias using LLM analysis."""
    logger.info("Starting bias scoring batch...")

    async def _run():
        from app.services.bias_scoring import score_unscored_articles

        async with async_session() as db:
            return await score_unscored_articles(db)

    stats = run_async(_run())
    logger.info(f"Bias scoring complete: {stats}")
    return stats

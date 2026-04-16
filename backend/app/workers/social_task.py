"""Celery tasks for Telegram social media monitoring."""

import asyncio
import logging

from app.database import async_session
from app.workers.celery_app import celery_app
from app.workers.task_lock import single_flight

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.social_task.ingest_telegram_task",
    bind=True,
    time_limit=600,        # 10 min (Telegram API)
    soft_time_limit=570,
)
@single_flight("ingest_telegram", timeout=660)
def ingest_telegram_task(self):
    """Fetch new posts from all tracked Telegram channels."""
    logger.info("Starting Telegram ingestion...")

    async def _run():
        from app.services.telegram_service import ingest_all_channels

        async with async_session() as db:
            return await ingest_all_channels(db)

    stats = run_async(_run())
    logger.info(f"Telegram ingestion complete: {stats}")
    return stats


@celery_app.task(
    name="app.workers.social_task.link_posts_task",
    bind=True,
    time_limit=600,
    soft_time_limit=570,
)
@single_flight("link_telegram_posts", timeout=660)
def link_posts_task(self):
    """Try to link unlinked Telegram posts to news stories."""
    logger.info("Linking unlinked Telegram posts...")

    async def _run():
        from app.services.telegram_service import link_unlinked_posts

        async with async_session() as db:
            return await link_unlinked_posts(db)

    linked = run_async(_run())
    logger.info(f"Linked {linked} posts")
    return {"linked": linked}


@celery_app.task(
    name="app.workers.social_task.compute_sentiment_task",
    bind=True,
    time_limit=600,
    soft_time_limit=570,
)
@single_flight("compute_social_sentiment", timeout=660)
def compute_sentiment_task(self):
    """Compute social sentiment snapshots for recent stories."""
    logger.info("Computing social sentiment snapshots...")

    async def _run():
        from sqlalchemy import select

        from app.models.story import Story
        from app.services.telegram_service import compute_story_social_sentiment

        async with async_session() as db:
            # Get stories with linked posts
            result = await db.execute(
                select(Story)
                .order_by(Story.trending_score.desc())
                .limit(50)
            )
            stories = result.scalars().all()

            computed = 0
            for story in stories:
                result = await compute_story_social_sentiment(story.id, db)
                if result:
                    computed += 1

            return {"computed": computed}

    stats = run_async(_run())
    logger.info(f"Sentiment computation complete: {stats}")
    return stats

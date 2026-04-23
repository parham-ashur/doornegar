"""One-shot: run cluster_articles and print stats.

Used to verify the cluster_attempts bump fix without waiting for
the next cron. Runs the same function the cron calls; pay the same
OpenAI cost, so don't call this casually.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    from sqlalchemy import func, select
    from app.database import async_session
    from app.models.article import Article
    from app.services.clustering import cluster_articles

    t0 = datetime.now(timezone.utc)
    print(f"[{t0.isoformat()}] starting cluster_articles()")

    # Snapshot before
    async with async_session() as db:
        before = (await db.execute(
            select(Article.cluster_attempts, func.count(Article.id))
            .where(Article.story_id.is_(None))
            .group_by(Article.cluster_attempts)
            .order_by(Article.cluster_attempts)
        )).all()
    print(f"before: {dict(before)}")

    async with async_session() as db:
        stats = await cluster_articles(db)

    t1 = datetime.now(timezone.utc)
    print(f"\n[{t1.isoformat()}] finished. elapsed={(t1 - t0).total_seconds():.1f}s")
    print(f"stats: {stats}")

    # Snapshot after
    async with async_session() as db:
        after = (await db.execute(
            select(Article.cluster_attempts, func.count(Article.id))
            .where(Article.story_id.is_(None))
            .group_by(Article.cluster_attempts)
            .order_by(Article.cluster_attempts)
        )).all()
    print(f"after: {dict(after)}")


if __name__ == "__main__":
    asyncio.run(main())

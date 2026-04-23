"""One-shot: run the Telegram ingest immediately.

Equivalent to step_ingest's Telegram portion (seed + ingest channels
+ convert posts to articles + aggregator extraction) so we don't
have to wait for the next 6h cron fire after restoring the session.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.database import async_session
    from app.services.telegram_service import (
        convert_telegram_posts_to_articles,
        extract_articles_from_aggregators,
        ingest_all_channels,
    )

    async with async_session() as db:
        print("seeding channels...")
        try:
            from app.services.seed_telegram import seed_telegram_channels
            seeded = await seed_telegram_channels(db)
            print(f"  seeded: {seeded}")
        except Exception as e:
            print(f"  seed skipped: {e}")

        print("ingesting all channels...")
        tg_stats = await ingest_all_channels(db)
        print(f"  {tg_stats}")

        print("converting posts to articles...")
        convert_stats = await convert_telegram_posts_to_articles(db)
        print(f"  {convert_stats}")

        print("extracting from aggregators...")
        agg_stats = await extract_articles_from_aggregators(db)
        print(f"  {agg_stats}")

    print("\ndone.")


if __name__ == "__main__":
    asyncio.run(main())

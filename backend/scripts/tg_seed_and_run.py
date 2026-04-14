"""Seed Telegram channels and fetch posts."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from app.database import async_session, engine, Base
    import app.models  # noqa — register all models

    print("=== Step 0: Adding missing columns ===")
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Add is_aggregator if missing
        await conn.execute(text("""
            ALTER TABLE telegram_channels
            ADD COLUMN IF NOT EXISTS is_aggregator BOOLEAN DEFAULT FALSE
        """))
        # Add last_message_id if missing
        await conn.execute(text("""
            ALTER TABLE telegram_channels
            ADD COLUMN IF NOT EXISTS last_message_id INTEGER
        """))
    print("Columns synced")

    from app.services.seed_telegram import seed_telegram_channels

    print("\n=== Step 1: Seeding Telegram channels ===")
    async with async_session() as db:
        count = await seed_telegram_channels(db)
        print(f"Seeded {count} new channels")

    print("\n=== Step 2: Fetching posts from channels ===")
    from app.services.telegram_service import ingest_all_channels
    async with async_session() as db:
        stats = await ingest_all_channels(db)
        print(f"Ingest stats: {stats}")

    print("\n=== Step 3: Converting mapped posts to articles ===")
    from app.services.telegram_service import convert_telegram_posts_to_articles
    async with async_session() as db:
        stats = await convert_telegram_posts_to_articles(db)
        print(f"Convert stats: {stats}")

    print("\n=== Step 4: Extracting links from aggregators ===")
    from app.services.telegram_service import extract_articles_from_aggregators
    async with async_session() as db:
        stats = await extract_articles_from_aggregators(db)
        print(f"Aggregator stats: {stats}")

    print("\n=== Done! ===")

if __name__ == "__main__":
    asyncio.run(main())

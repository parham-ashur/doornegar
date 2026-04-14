"""Add telegram_analysis column and pre-cache analyses for top stories."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from sqlalchemy import text, select, func
    from app.database import async_session, engine
    from app.models.social import TelegramPost
    from app.models.story import Story
    from app.services.telegram_analysis import analyze_story_telegram

    # Add column if missing
    print("=== Adding telegram_analysis column ===")
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE stories
            ADD COLUMN IF NOT EXISTS telegram_analysis JSONB
        """))
    print("Done")

    # Find top stories with telegram posts and cache their analyses
    print("\n=== Pre-caching analyses ===")
    async with async_session() as db:
        result = await db.execute(
            select(Story.id, Story.title_fa, func.count(TelegramPost.id).label("pc"))
            .join(TelegramPost, TelegramPost.story_id == Story.id)
            .where(TelegramPost.text.isnot(None))
            .group_by(Story.id, Story.title_fa)
            .having(func.count(TelegramPost.id) >= 2)
            .order_by(func.count(TelegramPost.id).desc())
            .limit(15)
        )
        stories = result.all()

        cached = 0
        for sid, title, count in stories:
            print(f"  [{count} posts] {(title or '')[:45]}...", end=" ")
            analysis = await analyze_story_telegram(db, str(sid))
            if analysis:
                story = await db.get(Story, sid)
                if story:
                    story.telegram_analysis = analysis
                    cached += 1
                    print("✓")
            else:
                print("-")
        await db.commit()
        print(f"\nCached {cached} analyses")

if __name__ == "__main__":
    asyncio.run(main())

"""
One-shot cleanup for story 420a996a — the zero-embedding mega-cluster.
Detaches articles + telegram_posts, deletes sentiment snapshots, removes the story.
Run: railway run --service doornegar python scripts/purge_mega_cluster.py --apply
"""
import argparse
import asyncio
from sqlalchemy import text
from app.database import async_session

STORY_ID = "420a996a-0d4e-44bb-9ae6-8b7bcf53e16a"


async def main(apply: bool) -> None:
    async with async_session() as db:
        r = await db.execute(
            text("SELECT COUNT(*) FROM articles WHERE story_id = :sid"),
            {"sid": STORY_ID},
        )
        a_count = r.scalar() or 0

        r = await db.execute(
            text("SELECT COUNT(*) FROM telegram_posts WHERE story_id = :sid"),
            {"sid": STORY_ID},
        )
        tp_count = r.scalar() or 0

        r = await db.execute(
            text("SELECT COUNT(*) FROM social_sentiment_snapshots WHERE story_id = :sid"),
            {"sid": STORY_ID},
        )
        ss_count = r.scalar() or 0

        print(f"articles to detach:            {a_count:>6}")
        print(f"telegram_posts to detach:      {tp_count:>6}")
        print(f"sentiment snapshots to delete: {ss_count:>6}")
        print(f"story row to delete:           1  ({STORY_ID})")

        if not apply:
            print("\nDRY RUN — rerun with --apply to execute.")
            return

    print("\nApplying...")
    async with async_session() as db:
        res = await db.execute(
            text(
                "UPDATE articles SET story_id = NULL, cluster_attempts = 0 "
                "WHERE story_id = :sid"
            ),
            {"sid": STORY_ID},
        )
        print(f"  articles detached:   {res.rowcount}")
        await db.commit()

    async with async_session() as db:
        res = await db.execute(
            text("UPDATE telegram_posts SET story_id = NULL WHERE story_id = :sid"),
            {"sid": STORY_ID},
        )
        print(f"  tg posts detached:   {res.rowcount}")
        await db.commit()

    async with async_session() as db:
        res = await db.execute(
            text("DELETE FROM social_sentiment_snapshots WHERE story_id = :sid"),
            {"sid": STORY_ID},
        )
        print(f"  snapshots deleted:   {res.rowcount}")
        await db.commit()

    async with async_session() as db:
        res = await db.execute(
            text("DELETE FROM stories WHERE id = :sid"),
            {"sid": STORY_ID},
        )
        print(f"  story deleted:       {res.rowcount}")
        await db.commit()

    print("\nDone.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.apply))

"""Test: does the cluster_attempts bump actually work?

Targets a single real orphan article, applies the same UPDATE the
production clustering code does, commits, and re-reads to confirm
the value changed.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from sqlalchemy import select, update
    from app.database import async_session
    from app.models.article import Article

    async with async_session() as db:
        row = (await db.execute(
            select(Article.id, Article.cluster_attempts)
            .where(Article.story_id.is_(None))
            .limit(1)
        )).one_or_none()
        if not row:
            print("no orphan to test with")
            return

        aid = row.id
        before = row.cluster_attempts
        print(f"target article: {aid}  cluster_attempts={before}")

        await db.execute(
            update(Article)
            .where(Article.id.in_([aid]))
            .values(cluster_attempts=Article.cluster_attempts + 1)
        )
        await db.commit()
        print("UPDATE executed + committed")

    async with async_session() as db2:
        row2 = (await db2.execute(
            select(Article.cluster_attempts).where(Article.id == aid)
        )).one()
        after = row2.cluster_attempts
        print(f"read-back: cluster_attempts={after}")
        print(f"delta: {before} -> {after}  ({'WORKED' if after > before else 'DID NOT WORK'})")

        # Reset so this isn't a stateful side-effect
        await db2.execute(
            update(Article).where(Article.id == aid).values(cluster_attempts=before)
        )
        await db2.commit()
        print(f"reset to original value {before}")


if __name__ == "__main__":
    asyncio.run(main())

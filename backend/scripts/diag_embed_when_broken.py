"""When did embeddings break? Sample by age."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from sqlalchemy import select, func
    from app.database import async_session
    from app.models.article import Article

    now = datetime.now(timezone.utc)

    async with async_session() as db:
        windows = [
            ("<1d",  now - timedelta(days=1), None),
            ("1-3d", now - timedelta(days=3), now - timedelta(days=1)),
            ("3-7d", now - timedelta(days=7), now - timedelta(days=3)),
            ("7-14d", now - timedelta(days=14), now - timedelta(days=7)),
            ("14-30d", now - timedelta(days=30), now - timedelta(days=14)),
            ("30-60d", now - timedelta(days=60), now - timedelta(days=30)),
            ("60-180d", now - timedelta(days=180), now - timedelta(days=60)),
        ]
        print(f"{'window':>10} | {'total':>6} | {'w/emb':>6} | {'all_zero':>9} | {'all_zero %':>10}")
        print("-" * 60)
        for label, lo, hi in windows:
            q = select(Article.id, Article.embedding).where(Article.ingested_at >= lo if lo else Article.id == Article.id)
            if hi is not None:
                q = q.where(Article.ingested_at < hi)
            rows = (await db.execute(q.limit(200))).all()
            total = len(rows)
            with_emb = sum(1 for _, e in rows if e is not None)
            all_zero = sum(1 for _, e in rows if e is not None and not any(v != 0.0 for v in e))
            pct = 100 * all_zero / max(1, with_emb)
            print(f"{label:>10} | {total:>6} | {with_emb:>6} | {all_zero:>9} | {pct:>9.1f}%")

        # sample one recent and one older article — show nonzero dims
        print("\n=== Sample: newest article ===")
        row = (await db.execute(
            select(Article.id, Article.title_fa, Article.ingested_at, Article.embedding)
            .order_by(Article.ingested_at.desc()).limit(1)
        )).one()
        nz = sum(1 for v in (row.embedding or []) if v != 0.0)
        print(f"  id={row.id} at={row.ingested_at}  nonzero_dims={nz}/{len(row.embedding or [])}")
        print(f"  title: {(row.title_fa or '')[:70]}")

        print("\n=== Sample: article from 45 days ago ===")
        target = now - timedelta(days=45)
        row = (await db.execute(
            select(Article.id, Article.title_fa, Article.ingested_at, Article.embedding)
            .where(Article.ingested_at <= target)
            .order_by(Article.ingested_at.desc()).limit(1)
        )).one_or_none()
        if row:
            nz = sum(1 for v in (row.embedding or []) if v != 0.0)
            print(f"  id={row.id} at={row.ingested_at}  nonzero_dims={nz}/{len(row.embedding or [])}")
            print(f"  title: {(row.title_fa or '')[:70]}")


if __name__ == "__main__":
    asyncio.run(main())

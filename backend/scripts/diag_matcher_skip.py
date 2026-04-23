"""Why is clustering.match_existing making 0 LLM calls?

Two plausible root causes:
  (a) every article is auto-rejected (cosine<0.60 or age>7d) — usually
      because embeddings are missing or zero
  (b) cluster_attempts isn't bumping, so no-op writes
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from sqlalchemy import func, select, text
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    async with async_session() as db:
        # Embedding coverage on orphan articles
        total_orph = (await db.execute(
            select(func.count(Article.id)).where(Article.story_id.is_(None))
        )).scalar() or 0
        with_emb = (await db.execute(
            select(func.count(Article.id)).where(
                Article.story_id.is_(None),
                Article.embedding.isnot(None),
            )
        )).scalar() or 0
        print(f"Orphans total: {total_orph}")
        print(f"  with any embedding JSONB: {with_emb}")

        # Sample 5 recent orphans — do their embeddings look real (non-zero)?
        rows = (await db.execute(
            select(Article.id, Article.title_fa, Article.embedding, Article.ingested_at)
            .where(Article.story_id.is_(None))
            .order_by(Article.ingested_at.desc())
            .limit(5)
        )).all()
        print("\nRecent orphan sample:")
        for r in rows:
            emb = r.embedding
            shape = "None" if emb is None else f"len={len(emb)}"
            nonzero = 0 if not emb else sum(1 for v in emb[:50] if v != 0)
            print(f"  {r.ingested_at:%Y-%m-%d %H:%M}  emb={shape} nonzero_first50={nonzero}  "
                  f"{(r.title_fa or '')[:60]}")

        # Candidate stories the matcher would consider
        from app.config import settings
        max_size = settings.max_cluster_size
        window = settings.clustering_time_window_days
        print(f"\nMatcher candidate pool (article_count 5..{max_size-1}, active within {window}d):")
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=window)
        cand = (await db.execute(
            select(func.count(Story.id)).where(
                Story.article_count >= 5,
                Story.article_count < max_size,
                Story.last_updated_at >= cutoff,
            )
        )).scalar() or 0
        has_centroid = (await db.execute(
            select(func.count(Story.id)).where(
                Story.article_count >= 5,
                Story.article_count < max_size,
                Story.last_updated_at >= cutoff,
                Story.centroid_embedding.isnot(None),
            )
        )).scalar() or 0
        print(f"  stories in window: {cand}")
        print(f"  with centroid:     {has_centroid}")

        # Recent pipeline stats from llm_usage_logs — last 24h of every purpose
        print("\nAll LLM purposes last 24h:")
        rows = (await db.execute(text(
            """
            SELECT purpose,
                   count(*) AS calls,
                   coalesce(sum(total_cost), 0) AS usd,
                   coalesce(sum(input_tokens), 0) AS in_tok
            FROM llm_usage_logs
            WHERE timestamp >= NOW() - interval '24 hours'
            GROUP BY purpose
            ORDER BY usd DESC
            """
        ))).all()
        for r in rows:
            print(f"  {r.purpose:40s} calls={r.calls:>5}  ${r.usd:>6.2f}  input_tok={r.in_tok:>10,}")

        # Has the cluster_attempts column been migrated? Column should exist
        # since main.py self-heals, but let's verify.
        col_check = (await db.execute(text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'cluster_attempts'
            """
        ))).all()
        print(f"\ncluster_attempts column: {col_check}")

        # Sample cluster_attempts values across all articles (not just orphans)
        rows = (await db.execute(
            select(Article.cluster_attempts, func.count(Article.id))
            .group_by(Article.cluster_attempts)
            .order_by(Article.cluster_attempts)
        )).all()
        print("cluster_attempts across ALL articles:")
        for r in rows:
            print(f"  attempts={r[0]}: {r[1]}")


if __name__ == "__main__":
    asyncio.run(main())

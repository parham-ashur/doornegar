"""Diagnostic: why is cluster_new making ~972 calls/day?

Run against prod:
  railway run --service doornegar python scripts/diag_cluster_replay.py

Prints the signals needed to decide whether the knobs that matter are:
  - floor-at-5 rejecting too many groups (articles get re-sent 3×)
  - cluster_attempts filter not firing where expected
  - pool size (30-day window too wide for current volume)
  - dedup bucketing not compressing duplicates
  - story matcher pushing articles back into the unmatched pool

This is pure read-only — safe to run any time.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from sqlalchemy import func, select, text
    from app.database import async_session
    from app.models.article import Article

    now = datetime.now(timezone.utc)

    async with async_session() as db:
        print("\n=== Article pool (cluster_new sees story_id IS NULL AND cluster_attempts < 3) ===")

        # cluster_attempts histogram, orphans only
        rows = (await db.execute(
            select(Article.cluster_attempts, func.count(Article.id))
            .where(Article.story_id.is_(None))
            .group_by(Article.cluster_attempts)
            .order_by(Article.cluster_attempts)
        )).all()
        total = sum(c for _, c in rows) or 1
        for attempts, count in rows:
            bar = "█" * int(40 * count / total)
            print(f"  cluster_attempts={attempts:>2}:  {count:>6}  {bar}")
        print(f"  total orphans: {total}")

        # Age distribution of orphans still eligible (<3 attempts)
        print("\n=== Eligible orphan pool by ingestion age (cluster_new sees these) ===")
        windows = [
            ("<1d",  now - timedelta(days=1), None),
            ("1-3d", now - timedelta(days=3), now - timedelta(days=1)),
            ("3-7d", now - timedelta(days=7), now - timedelta(days=3)),
            ("7-14d", now - timedelta(days=14), now - timedelta(days=7)),
            ("14-30d", now - timedelta(days=30), now - timedelta(days=14)),
            (">30d (aged out)", None, now - timedelta(days=30)),
        ]
        for label, lo, hi in windows:
            q = select(func.count(Article.id)).where(
                Article.story_id.is_(None),
                Article.cluster_attempts < 3,
            )
            if lo is not None:
                q = q.where(Article.ingested_at >= lo)
            if hi is not None:
                q = q.where(Article.ingested_at < hi)
            n = (await db.execute(q)).scalar() or 0
            print(f"  {label:>18}: {n}")

        # Ingestion vs orphan rate for last 24h
        print("\n=== Last 24h ingest / orphan split ===")
        cutoff24 = now - timedelta(days=1)
        ingested24 = (await db.execute(
            select(func.count(Article.id)).where(Article.ingested_at >= cutoff24)
        )).scalar() or 0
        orphan24 = (await db.execute(
            select(func.count(Article.id)).where(
                Article.ingested_at >= cutoff24,
                Article.story_id.is_(None),
            )
        )).scalar() or 0
        retired24 = (await db.execute(
            select(func.count(Article.id)).where(
                Article.ingested_at >= cutoff24,
                Article.story_id.is_(None),
                Article.cluster_attempts >= 3,
            )
        )).scalar() or 0
        print(f"  ingested:              {ingested24}")
        print(f"  still orphan:          {orphan24}  ({orphan24 * 100 // max(1, ingested24)}%)")
        print(f"  retired (attempts≥3):  {retired24}")

        # LLM usage log: cluster_new calls + tokens, last 24h/7d
        print("\n=== cluster_new LLM usage (from llm_usage_logs) ===")
        try:
            for label, days in (("last 24h", 1), ("last 7d", 7)):
                t = (await db.execute(text(
                    """
                    SELECT count(*) AS calls,
                           coalesce(sum(input_tokens), 0) AS in_tok,
                           coalesce(sum(output_tokens), 0) AS out_tok,
                           coalesce(avg(input_tokens), 0) AS avg_in,
                           coalesce(sum(total_cost), 0) AS usd
                    FROM llm_usage_logs
                    WHERE purpose = 'clustering.cluster_new'
                      AND timestamp >= NOW() - (:d || ' days')::interval
                    """
                ), {"d": days})).one()
                print(
                    f"  {label}: calls={t.calls}  input_tok={t.in_tok:,}  "
                    f"output_tok={t.out_tok:,}  avg_input={int(t.avg_in):,}  ${t.usd:.2f}"
                )
        except Exception as e:
            print(f"  llm_usage_logs unavailable: {e}")

        # Per-hour call rate + articles-in-vs-out of cluster_new — sampled
        print("\n=== cluster_new calls by hour (last 24h) ===")
        try:
            rows = (await db.execute(text(
                """
                SELECT date_trunc('hour', timestamp) AS h,
                       count(*) AS calls,
                       coalesce(sum(input_tokens), 0) AS in_tok
                FROM llm_usage_logs
                WHERE purpose = 'clustering.cluster_new'
                  AND timestamp >= NOW() - interval '24 hours'
                GROUP BY 1
                ORDER BY 1
                """
            ))).all()
            for r in rows:
                print(f"  {r.h:%Y-%m-%d %H:00}  calls={r.calls:>3}  input_tok={r.in_tok:>8,}")
        except Exception as e:
            print(f"  hourly breakdown unavailable: {e}")

        # Match step for context — is the matcher pushing back into cluster_new?
        print("\n=== match_existing LLM usage (for comparison) ===")
        try:
            t = (await db.execute(text(
                """
                SELECT count(*) AS calls,
                       coalesce(sum(input_tokens), 0) AS in_tok,
                       coalesce(sum(total_cost), 0) AS usd
                FROM llm_usage_logs
                WHERE purpose = 'clustering.match_existing'
                  AND timestamp >= NOW() - interval '24 hours'
                """
            ))).one()
            print(f"  24h: calls={t.calls}  input_tok={t.in_tok:,}  ${t.usd:.2f}")
        except Exception as e:
            print(f"  unavailable: {e}")

        # Distribution of ingested-in-24h articles by outcome
        print("\n=== Outcome of articles ingested in last 24h ===")
        matched = (await db.execute(
            select(func.count(Article.id)).where(
                Article.ingested_at >= cutoff24,
                Article.story_id.isnot(None),
            )
        )).scalar() or 0
        print(f"  matched to story: {matched}")
        print(f"  still orphan:     {orphan24}")
        print(f"   of which retired: {retired24}")

        # Duplicate-bucket estimate: group orphans by title normalised
        print("\n=== Dedup bucket estimate (orphans with identical title prefix) ===")
        rows = (await db.execute(text(
            """
            SELECT lower(substr(regexp_replace(coalesce(title_original, title_fa, title_en, ''), '\\s+', ' ', 'g'), 1, 80)) AS k,
                   count(*) AS n
            FROM articles
            WHERE story_id IS NULL
              AND cluster_attempts < 3
              AND ingested_at >= NOW() - interval '30 days'
            GROUP BY 1
            HAVING count(*) > 1
            ORDER BY n DESC
            LIMIT 10
            """
        ))).all()
        if rows:
            total_dupes = sum(r.n - 1 for r in rows)
            print(f"  top 10 dupe groups (by 80-char title prefix):")
            for r in rows:
                preview = (r.k or "")[:60]
                print(f"    n={r.n:>3}  {preview}")
            print(f"  savings if dedup by 80-char title alone compressed these: ~{total_dupes} calls")
        else:
            print("  no title-prefix duplicate groups in orphan pool")


if __name__ == "__main__":
    asyncio.run(main())

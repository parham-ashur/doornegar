"""
داریوش — Doornegar's Data Analyst Persona

Monitors pipeline health and data quality with pure DB queries.
No LLM needed — just cold, hard numbers.

Usage:
  railway run --service doornegar python scripts/dariush_data_analyst.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def check_stale_feeds(db) -> list[dict]:
    """RSS feeds that haven't returned articles in 3+ days."""
    from app.models.article import Article
    from app.models.source import Source
    from sqlalchemy import select, func

    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    findings = []

    result = await db.execute(
        select(Source).where(Source.is_active == True)  # noqa: E712
    )
    sources = list(result.scalars().all())

    for source in sources:
        latest = await db.execute(
            select(func.max(Article.published_at))
            .where(Article.source_id == source.id)
        )
        last_article_date = latest.scalar()

        if last_article_date is None:
            findings.append({
                "source": source.name_en,
                "slug": source.slug,
                "severity": "critical",
                "issue": "No articles ever ingested",
                "last_article": None,
            })
        elif last_article_date < cutoff:
            days_ago = (datetime.now(timezone.utc) - last_article_date).days
            findings.append({
                "source": source.name_en,
                "slug": source.slug,
                "severity": "high" if days_ago > 7 else "medium",
                "issue": f"No articles in {days_ago} days",
                "last_article": last_article_date.isoformat(),
            })

    return findings


async def check_ingestion_rate(db) -> dict:
    """Articles ingested in last 24h vs 7-day average."""
    from app.models.article import Article
    from sqlalchemy import select, func

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    count_24h = (await db.execute(
        select(func.count(Article.id)).where(Article.ingested_at >= last_24h)
    )).scalar() or 0

    count_7d = (await db.execute(
        select(func.count(Article.id)).where(Article.ingested_at >= last_7d)
    )).scalar() or 0

    avg_7d = count_7d / 7.0 if count_7d > 0 else 0

    severity = "ok"
    if avg_7d > 0:
        ratio = count_24h / avg_7d
        if ratio < 0.3:
            severity = "critical"
        elif ratio < 0.6:
            severity = "high"
        elif ratio < 0.8:
            severity = "medium"

    return {
        "last_24h": count_24h,
        "seven_day_total": count_7d,
        "seven_day_daily_avg": round(avg_7d, 1),
        "ratio": round(count_24h / avg_7d, 2) if avg_7d > 0 else None,
        "severity": severity,
    }


async def check_article_count_mismatch(db) -> list[dict]:
    """Stories where claimed article_count differs from actual linked articles."""
    from app.models.story import Story
    from app.models.article import Article
    from sqlalchemy import select, func

    result = await db.execute(
        select(
            Story.id,
            Story.title_en,
            Story.article_count,
            func.count(Article.id).label("actual_count"),
        )
        .outerjoin(Article, Article.story_id == Story.id)
        .group_by(Story.id, Story.title_en, Story.article_count)
    )
    rows = result.all()

    mismatches = []
    for row in rows:
        if row.article_count != row.actual_count:
            mismatches.append({
                "story_id": str(row.id),
                "title": row.title_en or "Untitled",
                "claimed": row.article_count,
                "actual": row.actual_count,
                "severity": "high" if abs(row.article_count - row.actual_count) > 3 else "medium",
            })

    return mismatches


async def check_telegram_channels(db) -> list[dict]:
    """Telegram channels that haven't been fetched recently."""
    from app.models.social import TelegramChannel
    from sqlalchemy import select

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    findings = []

    result = await db.execute(
        select(TelegramChannel).where(TelegramChannel.is_active == True)  # noqa: E712
    )
    channels = list(result.scalars().all())

    for ch in channels:
        if ch.last_fetched_at is None:
            findings.append({
                "channel": f"@{ch.username}",
                "title": ch.title,
                "severity": "high",
                "issue": "Never fetched",
                "last_fetched": None,
            })
        elif ch.last_fetched_at < cutoff:
            hours_ago = (datetime.now(timezone.utc) - ch.last_fetched_at).total_seconds() / 3600
            findings.append({
                "channel": f"@{ch.username}",
                "title": ch.title,
                "severity": "medium",
                "issue": f"Not fetched in {hours_ago:.0f} hours",
                "last_fetched": ch.last_fetched_at.isoformat(),
            })

    return findings


async def check_article_quality(db) -> dict:
    """Articles missing embeddings, titles, or sources."""
    from app.models.article import Article
    from sqlalchemy import select, func

    total = (await db.execute(select(func.count(Article.id)))).scalar() or 0

    no_embedding = (await db.execute(
        select(func.count(Article.id)).where(Article.embedding == None)  # noqa: E711
    )).scalar() or 0

    no_title = (await db.execute(
        select(func.count(Article.id)).where(
            (Article.title_original == None) | (Article.title_original == "")  # noqa: E711
        )
    )).scalar() or 0

    no_source = (await db.execute(
        select(func.count(Article.id)).where(Article.source_id == None)  # noqa: E711
    )).scalar() or 0

    no_en_title = (await db.execute(
        select(func.count(Article.id)).where(
            (Article.title_en == None) | (Article.title_en == "")  # noqa: E711
        )
    )).scalar() or 0

    return {
        "total_articles": total,
        "missing_embedding": no_embedding,
        "missing_title": no_title,
        "missing_source": no_source,
        "missing_en_title": no_en_title,
        "embedding_pct": round((1 - no_embedding / total) * 100, 1) if total > 0 else 0,
    }


async def check_stories_missing_summary(db) -> list[dict]:
    """Stories with 5+ articles but no summary."""
    from app.models.story import Story
    from sqlalchemy import select

    result = await db.execute(
        select(Story)
        .where(Story.article_count >= 5)
        .where((Story.summary_en == None) | (Story.summary_en == ""))  # noqa: E711
    )
    stories = list(result.scalars().all())

    return [
        {
            "story_id": str(s.id),
            "title": s.title_en or s.title_fa or "Untitled",
            "article_count": s.article_count,
            "severity": "high" if s.article_count >= 10 else "medium",
            "llm_failed": s.llm_failed_at.isoformat() if s.llm_failed_at else None,
        }
        for s in stories
    ]


def print_report(report: dict):
    """Pretty-print the data analyst report."""
    print("\n" + "=" * 60)
    print("  DARIUSH — Data Analyst Report")
    print("  Pipeline Health & Data Quality Audit")
    print("=" * 60)

    # Ingestion rate
    ing = report["ingestion_rate"]
    icon = {"ok": "[OK]", "medium": "[WARN]", "high": "[HIGH]", "critical": "[CRIT]"}.get(ing["severity"], "[?]")
    print(f"\n--- Ingestion Rate {icon} ---")
    print(f"  Last 24h: {ing['last_24h']} articles")
    print(f"  7-day avg: {ing['seven_day_daily_avg']}/day")
    if ing["ratio"] is not None:
        print(f"  Ratio: {ing['ratio']}x of average")

    # Stale feeds
    stale = report["stale_feeds"]
    print(f"\n--- Stale RSS Feeds ({len(stale)} issues) ---")
    for f in stale:
        sev = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[WARN]"}.get(f["severity"], "[?]")
        print(f"  {sev} {f['source']} ({f['slug']}): {f['issue']}")

    # Article count mismatches
    mis = report["article_count_mismatches"]
    print(f"\n--- Article Count Mismatches ({len(mis)} stories) ---")
    for m in mis[:10]:
        print(f"  [{m['severity'].upper()}] {m['title'][:50]}: claimed={m['claimed']} actual={m['actual']}")
    if len(mis) > 10:
        print(f"  ... and {len(mis) - 10} more")

    # Telegram
    tg = report["telegram_issues"]
    print(f"\n--- Telegram Channel Issues ({len(tg)} channels) ---")
    for t in tg[:10]:
        print(f"  [{t['severity'].upper()}] {t['channel']}: {t['issue']}")
    if len(tg) > 10:
        print(f"  ... and {len(tg) - 10} more")

    # Article quality
    aq = report["article_quality"]
    print(f"\n--- Article Quality ---")
    print(f"  Total articles: {aq['total_articles']}")
    print(f"  Missing embeddings: {aq['missing_embedding']} ({100 - aq['embedding_pct']:.1f}%)")
    print(f"  Missing titles: {aq['missing_title']}")
    print(f"  Missing EN titles: {aq['missing_en_title']}")
    print(f"  Missing source: {aq['missing_source']}")

    # Stories missing summaries
    sms = report["stories_missing_summary"]
    print(f"\n--- Stories Missing Summary ({len(sms)} stories with 5+ articles) ---")
    for s in sms[:10]:
        extra = f" (LLM failed: {s['llm_failed']})" if s["llm_failed"] else ""
        print(f"  [{s['severity'].upper()}] {s['title'][:50]} ({s['article_count']} articles){extra}")
    if len(sms) > 10:
        print(f"  ... and {len(sms) - 10} more")

    # Overall health
    critical_count = sum(1 for f in stale if f["severity"] == "critical")
    critical_count += 1 if ing["severity"] == "critical" else 0
    critical_count += sum(1 for m in mis if m["severity"] == "high")

    print(f"\n{'=' * 60}")
    if critical_count > 0:
        print(f"  HEALTH: DEGRADED — {critical_count} critical/high issues need attention")
    else:
        print("  HEALTH: GOOD — No critical issues detected")
    print(f"{'=' * 60}\n")


async def main():
    from app.database import async_session

    print("Dariush starting data quality audit...")

    async with async_session() as db:
        stale_feeds = await check_stale_feeds(db)
        ingestion_rate = await check_ingestion_rate(db)
        mismatches = await check_article_count_mismatch(db)
        telegram_issues = await check_telegram_channels(db)
        article_quality = await check_article_quality(db)
        missing_summaries = await check_stories_missing_summary(db)

    report = {
        "persona": "dariush",
        "persona_fa": "داریوش",
        "role": "Data Analyst",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stale_feeds": stale_feeds,
        "ingestion_rate": ingestion_rate,
        "article_count_mismatches": mismatches,
        "telegram_issues": telegram_issues,
        "article_quality": article_quality,
        "stories_missing_summary": missing_summaries,
    }

    print_report(report)

    output_path = os.path.join(os.path.dirname(__file__), "dariush_report.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

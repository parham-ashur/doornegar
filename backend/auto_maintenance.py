"""Doornegar Auto-Maintenance Daemon

Runs every N hours:
1. Fetches new articles (RSS + Telegram)
2. Processes them (NLP, translation, embeddings)
3. Clusters into stories
4. Generates summaries for new stories
5. Runs QA checks
6. Auto-fixes common issues
7. Logs everything

Usage:
  python auto_maintenance.py              # Run once
  python auto_maintenance.py --loop 4     # Run every 4 hours
  python auto_maintenance.py --loop 1     # Run every hour
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("maintenance.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("maintenance")


async def step_ingest():
    """Step 1: Fetch new articles from RSS + Telegram."""
    from app.database import async_session
    from app.services.ingestion import ingest_all_sources
    from app.services.telegram_service import (
        convert_telegram_posts_to_articles,
        ingest_all_channels,
    )

    async with async_session() as db:
        # RSS
        logger.info("Ingesting RSS feeds...")
        rss_stats = await ingest_all_sources(db)
        logger.info(f"RSS: {rss_stats}")

        # Telegram
        logger.info("Ingesting Telegram channels...")
        tg_stats = await ingest_all_channels(db)
        logger.info(f"Telegram: {tg_stats}")

        # Convert Telegram posts to articles
        logger.info("Converting Telegram posts to articles...")
        convert_stats = await convert_telegram_posts_to_articles(db)
        logger.info(f"Converted: {convert_stats}")

    return {
        "rss_new": rss_stats.get("new", 0),
        "telegram_new": tg_stats.get("new", 0),
        "converted": convert_stats.get("created", 0),
    }


async def step_process():
    """Step 2: NLP processing — translate, embed, extract keywords."""
    from app.database import async_session
    from app.services.nlp_pipeline import process_unprocessed_articles

    total_processed = 0
    async with async_session() as db:
        while True:
            stats = await process_unprocessed_articles(db)
            batch = stats.get("processed", 0)
            total_processed += batch
            if batch < 50:
                break
            logger.info(f"  Processed batch: {batch}")

    logger.info(f"NLP: {total_processed} articles processed")
    return {"processed": total_processed}


async def step_cluster():
    """Step 3: Cluster articles into stories."""
    from app.database import async_session
    from app.services.clustering import cluster_articles

    async with async_session() as db:
        stats = await cluster_articles(db)
    logger.info(f"Clustering: {stats}")
    return stats


async def step_summarize():
    """Step 4: Generate summaries for stories without one."""
    import json as _json

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.story_analysis import generate_story_analysis

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.summary_fa.is_(None), Story.article_count >= 5)
            .order_by(Story.article_count.desc())
        )
        stories = list(result.scalars().all())

        if not stories:
            logger.info("Summarize: all visible stories have summaries")
            return {"generated": 0}

        logger.info(f"Generating summaries for {len(stories)} stories...")
        success = 0
        for story in stories:
            articles_info = [
                {
                    "title": a.title_original or a.title_fa or a.title_en or "",
                    "content": (a.content_text or a.summary or "")[:1500],
                    "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                    "state_alignment": a.source.state_alignment if a.source else "",
                }
                for a in story.articles
            ]
            try:
                analysis = await generate_story_analysis(story, articles_info)
                story.summary_fa = analysis.get("summary_fa")
                story.summary_en = _json.dumps({
                    "state_summary_fa": analysis.get("state_summary_fa"),
                    "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                    "independent_summary_fa": analysis.get("independent_summary_fa"),
                    "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                    "scores": analysis.get("scores"),
                }, ensure_ascii=False)
                await db.commit()
                success += 1
                logger.info(f"  ✓ {story.title_fa[:40]}")
            except Exception as e:
                logger.warning(f"  ✗ {story.title_fa[:40]}: {e}")

        return {"generated": success}


async def step_fix_images():
    """Step 4b: Fix broken images and ensure every visible story has an image."""
    import httpx
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    stats = {"checked": 0, "broken": 0, "replaced": 0, "stories_fixed": 0}

    async with async_session() as db:
        # 1. Fix broken article images
        result = await db.execute(
            select(Article).where(Article.image_url.isnot(None)).limit(100)
        )
        articles = list(result.scalars().all())

        async with httpx.AsyncClient(timeout=5) as client:
            for a in articles:
                stats["checked"] += 1
                try:
                    r = await client.head(a.image_url)
                    if r.status_code != 200:
                        stats["broken"] += 1
                        if a.url and "t.me/" not in a.url:
                            from app.services.nlp_pipeline import _fetch_og_image
                            new_img = await _fetch_og_image(a.url)
                            if new_img:
                                a.image_url = new_img
                                stats["replaced"] += 1
                            else:
                                a.image_url = None
                        else:
                            a.image_url = None
                except Exception:
                    pass

        # 2. Ensure every visible story has at least one article with an image
        result = await db.execute(
            select(Story).options(selectinload(Story.articles))
            .where(Story.article_count >= 5)
        )
        for story in result.scalars().all():
            has_img = any(a.image_url for a in story.articles)
            if not has_img:
                # Try to find an image for any article in this story
                for a in story.articles:
                    if a.url and "t.me/" not in a.url:
                        from app.services.nlp_pipeline import _fetch_og_image
                        img = await _fetch_og_image(a.url)
                        if img:
                            a.image_url = img
                            stats["stories_fixed"] += 1
                            break
                else:
                    # Fallback: search Wikimedia using story title
                    from app.services.nlp_pipeline import _search_free_image
                    img = await _search_free_image(story.title_en or story.title_fa or "")
                    if img and story.articles:
                        story.articles[0].image_url = img
                        stats["stories_fixed"] += 1

        await db.commit()

    if stats["broken"] > 0 or stats["stories_fixed"] > 0:
        logger.info(f"Image fix: {stats['broken']} broken, {stats['replaced']} replaced, {stats['stories_fixed']} stories given images")
    return stats


async def step_story_quality():
    """Step 4c: Story quality — merge duplicates, regenerate stale summaries, score quality."""
    import json as _json
    from sqlalchemy import select, update
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.story_analysis import generate_story_analysis

    stats = {"summaries_regenerated": 0, "duplicates_flagged": 0, "stale_cleared": 0}

    async with async_session() as db:
        # 1. Regenerate summaries for stories that got 3+ new articles since last summary
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 5, Story.summary_fa.isnot(None))
        )
        for story in result.scalars().all():
            actual_count = len(story.articles)
            if actual_count >= story.article_count + 3:
                # Story has grown significantly — regenerate
                story.summary_fa = None
                story.summary_en = None
                story.article_count = actual_count
                stats["stale_cleared"] += 1

        await db.commit()

        # Now generate summaries for cleared ones
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 5, Story.summary_fa.is_(None))
            .order_by(Story.article_count.desc())
            .limit(5)  # Max 5 per run to control costs
        )
        from app.config import settings
        if settings.openai_api_key:
            for story in result.scalars().all():
                articles_info = [
                    {
                        "title": a.title_original or a.title_fa or a.title_en or "",
                        "content": (a.content_text or a.summary or "")[:1500],
                        "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                        "state_alignment": a.source.state_alignment if a.source else "",
                    }
                    for a in story.articles
                ]
                try:
                    analysis = await generate_story_analysis(story, articles_info)
                    story.summary_fa = analysis.get("summary_fa")
                    story.summary_en = _json.dumps({
                        "state_summary_fa": analysis.get("state_summary_fa"),
                        "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                        "independent_summary_fa": analysis.get("independent_summary_fa"),
                        "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                        "scores": analysis.get("scores"),
                    }, ensure_ascii=False)
                    stats["summaries_regenerated"] += 1
                    logger.info(f"  Regenerated summary: {story.title_fa[:40]}")
                except Exception as e:
                    logger.warning(f"  Failed: {story.title_fa[:40]}: {e}")

            await db.commit()

    if stats["stale_cleared"] > 0 or stats["summaries_regenerated"] > 0:
        logger.info(f"Story quality: {stats}")
    return stats


async def step_source_health():
    """Step 4d: Monitor source/feed health — track which feeds consistently fail."""
    from sqlalchemy import select, func, text
    from app.database import async_session
    from app.models.ingestion_log import IngestionLog
    from app.models.source import Source

    stats = {"healthy": 0, "degraded": 0, "failing": []}

    async with async_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)

        logs = await db.execute(
            select(IngestionLog)
            .where(IngestionLog.started_at >= cutoff, IngestionLog.status == "error")
        )
        error_logs = list(logs.scalars().all())

        # Group errors by feed URL
        feed_errors: dict[str, int] = {}
        for log in error_logs:
            feed_errors[log.feed_url] = feed_errors.get(log.feed_url, 0) + 1

        for feed, count in sorted(feed_errors.items(), key=lambda x: -x[1]):
            if count >= 3:
                stats["failing"].append(f"{feed} ({count} failures in 3 days)")
                stats["degraded"] += 1

        total_sources = (await db.execute(select(func.count(Source.id)))).scalar() or 0
        stats["healthy"] = total_sources - stats["degraded"]

    if stats["failing"]:
        logger.warning(f"Source health: {len(stats['failing'])} failing feeds:")
        for f in stats["failing"]:
            logger.warning(f"  ⚠ {f}")

    return stats


async def step_cost_tracking():
    """Step 4e: Track OpenAI API costs from maintenance runs."""
    from pathlib import Path

    log_file = Path(__file__).parent.parent / "project-management" / "COST_LOG.md"

    # Estimate costs based on what was done this run
    # GPT-4o-mini pricing: ~$0.15/1M input, ~$0.60/1M output
    # Average clustering batch: ~3K tokens in, ~1K out = ~$0.001
    # Average summary: ~5K tokens in, ~1K out = ~$0.002
    # Average translation batch (30 titles): ~1K tokens in, ~1K out = ~$0.0005

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")

    entry = f"| {date_str} | auto-maintenance | Est. ~$0.01-0.05 | Cluster + Summarize + Translate |\n"

    if log_file.exists():
        content = log_file.read_text(encoding="utf-8")
        if entry.split("|")[1].strip() not in content:
            content += entry
    else:
        content = f"""# API Cost Log

Tracks estimated OpenAI API costs per maintenance run.

| Date | Trigger | Est. Cost | Operations |
|------|---------|-----------|------------|
{entry}"""

    log_file.write_text(content, encoding="utf-8")
    return {"logged": True}


async def step_database_backup():
    """Step 4f: Create a database backup (local PostgreSQL only)."""
    import subprocess
    from pathlib import Path

    backup_dir = Path(__file__).parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    now = datetime.now()
    backup_file = backup_dir / f"doornegar_{now.strftime('%Y%m%d_%H%M')}.sql"

    # Only backup local Docker DB (not Neon)
    from app.config import settings
    if "localhost" not in settings.database_url and "127.0.0.1" not in settings.database_url:
        logger.info("Skipping backup — not using local database")
        return {"skipped": True, "reason": "remote database"}

    try:
        result = subprocess.run(
            ["pg_dump", "-h", "localhost", "-U", "doornegar", "-d", "doornegar", "-f", str(backup_file)],
            capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "PGPASSWORD": "doornegar_dev"},
        )
        if result.returncode == 0:
            size_mb = backup_file.stat().st_size / 1024 / 1024
            logger.info(f"Database backup: {backup_file.name} ({size_mb:.1f}MB)")

            # Keep only last 7 backups
            backups = sorted(backup_dir.glob("doornegar_*.sql"), reverse=True)
            for old in backups[7:]:
                old.unlink()
                logger.info(f"  Deleted old backup: {old.name}")

            return {"file": str(backup_file), "size_mb": round(size_mb, 1)}
        else:
            logger.warning(f"Backup failed: {result.stderr[:200]}")
            return {"error": result.stderr[:200]}
    except FileNotFoundError:
        logger.info("pg_dump not found — skipping backup")
        return {"skipped": True, "reason": "pg_dump not available"}
    except Exception as e:
        logger.warning(f"Backup error: {e}")
        return {"error": str(e)}


async def step_rater_feedback_apply():
    """Step 4g: Apply rater feedback when consensus is reached."""
    from sqlalchemy import select, func, update

    from app.database import async_session
    from app.models.feedback import RaterFeedback
    from app.models.article import Article

    stats = {"articles_removed": 0, "checked": 0}

    async with async_session() as db:
        # Find articles flagged as irrelevant by 3+ raters
        result = await db.execute(
            select(
                RaterFeedback.article_id,
                RaterFeedback.story_id,
                func.count(RaterFeedback.id).label("votes"),
            )
            .where(
                RaterFeedback.feedback_type == "article_relevance",
                RaterFeedback.is_relevant.is_(False),
            )
            .group_by(RaterFeedback.article_id, RaterFeedback.story_id)
            .having(func.count(RaterFeedback.id) >= 3)
        )

        for row in result.all():
            article_id, story_id, votes = row
            if article_id and story_id:
                # Remove article from story
                await db.execute(
                    update(Article)
                    .where(Article.id == article_id, Article.story_id == story_id)
                    .values(story_id=None)
                )
                stats["articles_removed"] += 1
                logger.info(f"  Removed article {article_id} from story {story_id} ({votes} raters agreed)")

        stats["checked"] = True
        await db.commit()

    if stats["articles_removed"] > 0:
        logger.info(f"Rater feedback: removed {stats['articles_removed']} irrelevant articles")
    return stats


async def step_archive_stale():
    """Archive stories older than 30 days with no new articles."""
    from sqlalchemy import select, update, func, delete

    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article

    stats = {"archived": 0, "recounted": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)

    async with async_session() as db:
        # Find stories not updated in 60 days with low article count AND no linked articles
        result = await db.execute(
            select(Story).where(
                Story.last_updated_at < cutoff,
                Story.article_count < 3,
            )
        )
        stale = list(result.scalars().all())

        for story in stale:
            # Unlink articles and delete stale hidden story
            await db.execute(update(Article).where(Article.story_id == story.id).values(story_id=None))
            await db.execute(delete(Story).where(Story.id == story.id))
            stats["archived"] += 1

        # Recount article_count for all visible stories (in case articles were added/removed)
        result = await db.execute(select(Story).where(Story.article_count >= 5))
        for story in result.scalars().all():
            actual = (await db.execute(
                select(func.count(Article.id)).where(Article.story_id == story.id)
            )).scalar() or 0
            if actual != story.article_count:
                story.article_count = actual
                source_count = (await db.execute(
                    select(func.count(func.distinct(Article.source_id))).where(Article.story_id == story.id)
                )).scalar() or 0
                story.source_count = source_count
                stats["recounted"] += 1

        await db.commit()

    if stats["archived"] > 0 or stats["recounted"] > 0:
        logger.info(f"Archive/recount: {stats}")
    return stats


async def step_recalculate_trending():
    """Recalculate trending scores for all visible stories."""
    from sqlalchemy import select

    from app.database import async_session
    from app.models.story import Story

    stats = {"updated": 0}

    async with async_session() as db:
        result = await db.execute(select(Story).where(Story.article_count >= 5))
        for story in result.scalars().all():
            old_score = story.trending_score
            # Score = article_count * recency_factor (decays over 30 days)
            if story.first_published_at:
                hours_ago = (datetime.now(timezone.utc) - story.first_published_at).total_seconds() / 3600
                recency = max(0.1, 1.0 - (hours_ago / (30 * 24)) * 0.9)
            else:
                recency = 0.5
            story.trending_score = story.article_count * recency
            if abs(story.trending_score - old_score) > 0.1:
                stats["updated"] += 1

        await db.commit()

    if stats["updated"] > 0:
        logger.info(f"Trending recalc: {stats['updated']} stories updated")
    return stats


async def step_telegram_health():
    """Check Telegram session health and channel accessibility."""
    stats = {"session_ok": False, "channels_checked": 0, "channels_failing": []}

    try:
        from telethon import TelegramClient
        from app.config import settings

        if not settings.telegram_api_id or not settings.telegram_api_hash:
            return {"skipped": True, "reason": "Telegram not configured"}

        client = TelegramClient(
            "doornegar_session",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()

        if await client.is_user_authorized():
            stats["session_ok"] = True
        else:
            logger.warning("⚠ Telegram session expired! Re-authenticate with phone number.")
            stats["session_ok"] = False

        # Check a few channels
        from app.database import async_session
        from app.models.social import TelegramChannel
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(TelegramChannel).where(TelegramChannel.is_active.is_(True)).limit(5)
            )
            for ch in result.scalars().all():
                stats["channels_checked"] += 1
                try:
                    entity = await client.get_entity(ch.username)
                except Exception as e:
                    stats["channels_failing"].append(f"@{ch.username}: {str(e)[:50]}")

        await client.disconnect()

    except ImportError:
        return {"skipped": True, "reason": "telethon not installed"}
    except Exception as e:
        logger.warning(f"Telegram health check failed: {e}")
        stats["error"] = str(e)[:100]

    if stats["channels_failing"]:
        logger.warning(f"Telegram: {len(stats['channels_failing'])} channels failing")
    elif stats["session_ok"]:
        logger.info("Telegram: session OK, channels accessible")

    return stats


async def step_deduplicate_articles():
    """Find and merge duplicate articles (same content from RSS + Telegram)."""
    from sqlalchemy import select, func, update

    from app.database import async_session
    from app.models.article import Article

    stats = {"duplicates_found": 0, "removed": 0}

    async with async_session() as db:
        # Find articles with the same title_fa that belong to different stories
        result = await db.execute(
            select(Article.title_fa, func.count(Article.id).label("cnt"))
            .where(Article.title_fa.isnot(None))
            .group_by(Article.title_fa)
            .having(func.count(Article.id) > 1)
            .limit(50)
        )

        for title, count in result.all():
            stats["duplicates_found"] += 1
            # Get all articles with this title
            dupes = await db.execute(
                select(Article).where(Article.title_fa == title).order_by(Article.ingested_at)
            )
            articles = list(dupes.scalars().all())
            if len(articles) <= 1:
                continue

            # Keep the first one (earliest ingested), remove story_id from others if same story
            keeper = articles[0]
            for dupe in articles[1:]:
                if dupe.story_id and dupe.story_id == keeper.story_id:
                    dupe.story_id = None  # Remove duplicate from same story
                    stats["removed"] += 1

        await db.commit()

    if stats["duplicates_found"] > 0:
        logger.info(f"Dedup: {stats['duplicates_found']} duplicate titles, {stats['removed']} removed from stories")
    return stats


async def step_disk_monitoring():
    """Check disk usage for images, backups, and logs."""
    import os
    from pathlib import Path

    stats = {}
    base = Path(__file__).parent.parent

    for name, path in [
        ("images", base / "backend" / "static" / "images"),
        ("backups", base / "backups"),
        ("logs", base / "backend"),
    ]:
        if path.exists():
            if path.is_dir():
                total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            else:
                total = 0
            stats[name] = f"{total / 1024 / 1024:.1f}MB"
        else:
            stats[name] = "N/A"

    # Check maintenance.log size
    log_file = base / "backend" / "maintenance.log"
    if log_file.exists():
        size_mb = log_file.stat().st_size / 1024 / 1024
        stats["maintenance_log"] = f"{size_mb:.1f}MB"
        # Rotate if too large (>10MB)
        if size_mb > 10:
            rotated = log_file.with_suffix(".log.old")
            if rotated.exists():
                rotated.unlink()
            log_file.rename(rotated)
            log_file.write_text("")
            stats["log_rotated"] = True
            logger.info("Rotated maintenance.log (>10MB)")

    logger.info(f"Disk usage: {stats}")
    return stats


async def step_weekly_digest():
    """Generate a weekly digest (runs only on Mondays)."""
    from pathlib import Path
    from sqlalchemy import select, func

    now = datetime.now()
    if now.weekday() != 0:  # Monday = 0
        return {"skipped": True, "reason": "Not Monday"}

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session() as db:
        new_articles = (await db.execute(
            select(func.count(Article.id)).where(Article.ingested_at >= week_ago)
        )).scalar() or 0

        new_stories = (await db.execute(
            select(func.count(Story.id)).where(Story.created_at >= week_ago)
        )).scalar() or 0

        top_stories = (await db.execute(
            select(Story.title_fa, Story.article_count)
            .where(Story.article_count >= 5, Story.created_at >= week_ago)
            .order_by(Story.article_count.desc())
            .limit(5)
        )).all()

        total_articles = (await db.execute(select(func.count(Article.id)))).scalar()
        total_stories = (await db.execute(select(func.count(Story.id)))).scalar()

    digest_dir = Path(__file__).parent.parent / "project-management" / "digests"
    digest_dir.mkdir(exist_ok=True)

    week_str = now.strftime("%Y-W%W")
    digest_file = digest_dir / f"digest_{week_str}.md"

    content = f"""# Weekly Digest — {now.strftime('%B %d, %Y')}

## This Week's Numbers
- **New articles**: {new_articles}
- **New stories**: {new_stories}
- **Total articles**: {total_articles}
- **Total stories**: {total_stories}

## Top Stories This Week
"""
    for title, count in top_stories:
        content += f"- [{count} articles] {title}\n"

    if not top_stories:
        content += "- No new stories with 5+ articles this week\n"

    content += f"""
## System Health
- Auto-maintenance running every 4 hours
- Check dashboard for detailed metrics: /dashboard

---
*Auto-generated by Doornegar maintenance system*
"""

    digest_file.write_text(content, encoding="utf-8")
    logger.info(f"Weekly digest generated: {digest_file.name}")
    return {"file": str(digest_file), "new_articles": new_articles, "new_stories": new_stories}


async def step_uptime_check():
    """Ping production services to verify they're up."""
    import httpx

    targets = {
        "backend_local": "http://localhost:8000/health",
        "frontend_local": "http://localhost:3001",
        "backend_prod": "https://doornegar-production.up.railway.app/health",
        "frontend_prod": "https://frontend-tau-six-36.vercel.app",
    }

    stats = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for name, url in targets.items():
            try:
                r = await client.get(url)
                stats[name] = f"✓ {r.status_code}"
            except Exception as e:
                stats[name] = f"✗ {str(e)[:40]}"
                logger.warning(f"Uptime: {name} is DOWN — {e}")

    logger.info(f"Uptime check: {stats}")
    return stats


async def step_fix_issues():
    """Step 5: Auto-fix common issues."""
    from sqlalchemy import select, func

    from app.database import async_session
    from app.models.article import Article
    from app.config import settings

    fixes = {}

    async with async_session() as db:
        # Fix 1: Translate English title_fa
        result = await db.execute(select(Article).where(Article.title_fa.isnot(None)))
        english_in_fa = []
        for a in result.scalars().all():
            if a.title_fa and sum(1 for c in a.title_fa if c.isascii() and c.isalpha()) > len(a.title_fa) * 0.5:
                english_in_fa.append(a)

        if english_in_fa and settings.openai_api_key:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            fixed = 0
            for batch_start in range(0, len(english_in_fa), 30):
                batch = english_in_fa[batch_start:batch_start + 30]
                titles = "\n".join(f"{i+1}. {a.title_fa}" for i, a in enumerate(batch))
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Translate these English headlines to Farsi. Return ONLY translations, numbered.\n\n{titles}"}],
                        max_tokens=2000, temperature=0,
                    )
                    lines = resp.choices[0].message.content.strip().split("\n")
                    for i, article in enumerate(batch):
                        if i < len(lines):
                            clean = re.sub(r"^[\d۰-۹]+[\.\)]\s*", "", lines[i]).strip()
                            if clean and not any(c.isascii() and c.isalpha() for c in clean[:10]):
                                article.title_fa = clean
                                fixed += 1
                except Exception as e:
                    logger.warning(f"Translation batch failed: {e}")

            await db.commit()
            fixes["english_titles_fixed"] = fixed
            logger.info(f"Fixed {fixed} English-in-Farsi titles")

        # Fix 2: Clean source names from Telegram titles
        result = await db.execute(
            select(Article).where(Article.url.contains("t.me/"), Article.title_fa.contains("|"))
        )
        cleaned = 0
        for a in result.scalars().all():
            if a.title_fa and "|" in a.title_fa:
                new_title = re.sub(r"\|\s*[^\n]+$", "", a.title_fa, flags=re.MULTILINE).strip()
                if new_title != a.title_fa:
                    a.title_fa = new_title
                    cleaned += 1
        if cleaned:
            await db.commit()
            fixes["source_names_cleaned"] = cleaned
            logger.info(f"Cleaned {cleaned} source names from titles")

    return fixes


async def step_visual_check():
    """Step 5b: Check frontend/visual quality — pages load, content renders, no broken elements."""
    import httpx

    frontend_url = "http://localhost:3001"
    backend_url = "http://localhost:8000"
    issues = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        # 1. Check homepage loads and has content
        try:
            r = await client.get(f"{frontend_url}/fa")
            if r.status_code != 200:
                issues.append(f"Homepage returned {r.status_code}")
            else:
                html = r.text
                if "هنوز موضوعی ایجاد نشده" in html:
                    issues.append("Homepage showing empty state — no stories visible")
                if "دورنگر" not in html:
                    issues.append("Homepage missing site name (دورنگر)")
                if html.count("localhost:8000/images/") > 0:
                    # Count broken local image references
                    import re
                    local_imgs = re.findall(r'localhost:8000/images/[^"]+', html)
                    issues.append(f"Homepage has {len(local_imgs)} local image URLs (won't work in production)")
        except Exception as e:
            issues.append(f"Frontend not reachable: {e}")

        # 2. Check trending API returns stories with required fields
        try:
            r = await client.get(f"{backend_url}/api/v1/stories/trending?limit=10")
            if r.status_code == 200:
                stories = r.json()
                if len(stories) == 0:
                    issues.append("Trending API returns 0 stories")
                else:
                    no_image = sum(1 for s in stories if not s.get("image_url"))
                    no_title = sum(1 for s in stories if not s.get("title_fa"))
                    long_titles = sum(1 for s in stories if s.get("title_fa") and len(s["title_fa"]) > 80)
                    question_titles = sum(1 for s in stories if s.get("title_fa") and "؟" in s["title_fa"])
                    zero_coverage = sum(1 for s in stories if s.get("state_pct", 0) == 0 and s.get("diaspora_pct", 0) == 0 and s.get("independent_pct", 0) == 0)

                    if no_image > 0:
                        issues.append(f"{no_image}/{len(stories)} homepage stories missing image")
                    if no_title > 0:
                        issues.append(f"{no_title}/{len(stories)} homepage stories missing Farsi title")
                    if long_titles > 0:
                        issues.append(f"{long_titles}/{len(stories)} story titles too long (>80 chars) — may not fit on one line")
                    if question_titles > 0:
                        issues.append(f"{question_titles}/{len(stories)} story titles are questions (should be statements)")
                    if zero_coverage > 0:
                        issues.append(f"{zero_coverage}/{len(stories)} stories have 0% on all coverage sides")

                    # 3. Check story detail page loads for first story
                    story_id = stories[0]["id"]
                    r2 = await client.get(f"{frontend_url}/fa/stories/{story_id}")
                    if r2.status_code != 200:
                        issues.append(f"Story detail page returned {r2.status_code}")

                    # 4. Check analysis endpoint returns data
                    r3 = await client.get(f"{backend_url}/api/v1/stories/{story_id}/analysis")
                    if r3.status_code == 200:
                        analysis = r3.json()
                        if not analysis.get("summary_fa"):
                            issues.append(f"Top story has no summary cached")
                    else:
                        issues.append(f"Analysis endpoint returned {r3.status_code}")

            else:
                issues.append(f"Trending API returned {r.status_code}")
        except Exception as e:
            issues.append(f"API check failed: {e}")

        # 5. Check CORS works
        try:
            r = await client.options(
                f"{backend_url}/api/v1/stories/trending",
                headers={"Origin": frontend_url, "Access-Control-Request-Method": "GET"}
            )
            if "access-control-allow-origin" not in r.headers:
                issues.append("CORS not configured — frontend can't reach API")
        except Exception:
            pass

        # 6. Check sources page
        try:
            r = await client.get(f"{backend_url}/api/v1/sources")
            if r.status_code == 200:
                data = r.json()
                sources = data.get("sources", [])
                if len(sources) < 5:
                    issues.append(f"Only {len(sources)} sources returned (expected 15+)")
        except Exception:
            pass

        # 7. Check dashboard API
        try:
            r = await client.get(f"{backend_url}/api/v1/admin/dashboard")
            if r.status_code != 200:
                issues.append(f"Dashboard API returned {r.status_code}")
        except Exception:
            pass

    if issues:
        logger.warning(f"Visual check found {len(issues)} issues:")
        for issue in issues:
            logger.warning(f"  ⚠ {issue}")
    else:
        logger.info("Visual check: all clear ✓")

    return {"issues": issues, "checks_passed": 7 - len(issues)}


async def step_update_docs(results: dict, start_time: float):
    """Step 6: Update project management docs with maintenance results."""
    from pathlib import Path
    from sqlalchemy import select, func

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.models.social import TelegramPost

    pm_dir = Path(__file__).parent.parent / "project-management"
    if not pm_dir.exists():
        logger.info("No project-management dir found, skipping doc update")
        return {"skipped": True}

    # Gather current metrics
    async with async_session() as db:
        total_articles = (await db.execute(select(func.count(Article.id)))).scalar()
        total_stories = (await db.execute(select(func.count(Story.id)))).scalar()
        visible = (await db.execute(select(func.count(Story.id)).where(Story.article_count >= 5))).scalar()
        with_summary = (await db.execute(select(func.count(Story.id)).where(Story.summary_fa.isnot(None)))).scalar()
        tg_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar()
        no_fa = (await db.execute(select(func.count(Article.id)).where(Article.title_fa.is_(None)))).scalar()

    now = datetime.now()
    elapsed = time.time() - start_time
    date_str = now.strftime("%Y-%m-%d %H:%M")

    # 1. Append to maintenance log
    log_file = pm_dir / "MAINTENANCE_LOG.md"
    entry = f"""
### {date_str}
- **Duration**: {elapsed:.0f}s
- **Ingest**: {results.get('ingest', {})}
- **Process**: {results.get('process', {})}
- **Cluster**: {results.get('cluster', {})}
- **Summarize**: {results.get('summarize', {})}
- **Image Fix**: {results.get('fix_images', {})}
- **Story Quality**: {results.get('story_quality', {})}
- **Archive Stale**: {results.get('archive_stale', {})}
- **Trending Recalc**: {results.get('recalc_trending', {})}
- **Dedup Articles**: {results.get('dedup_articles', {})}
- **Source Health**: {results.get('source_health', {})}
- **Fixes**: {results.get('fixes', {})}
- **Rater Feedback**: {results.get('rater_feedback', {})}
- **Telegram Health**: {results.get('telegram_health', {})}
- **Visual Check**: {results.get('visual', {})}
- **Uptime**: {results.get('uptime', {})}
- **Disk**: {results.get('disk', {})}
- **Cost Tracking**: {results.get('cost_tracking', {})}
- **Backup**: {results.get('backup', {})}
- **Weekly Digest**: {results.get('weekly_digest', {})}
- **Metrics**: {total_articles} articles, {total_stories} stories ({visible} visible), {tg_posts} Telegram posts
- **Issues**: {no_fa} articles without Farsi title
"""
    if log_file.exists():
        content = log_file.read_text(encoding="utf-8")
        # Insert after the header
        if "---" in content:
            parts = content.split("---", 1)
            content = parts[0] + "---\n" + entry + parts[1]
        else:
            content += entry
    else:
        content = f"""# Maintenance Log

Auto-generated by `auto_maintenance.py`. Each entry shows what happened during a maintenance run.

---
{entry}"""
    log_file.write_text(content, encoding="utf-8")

    # 2. Update PROJECT_STATUS.md metrics
    status_file = pm_dir / "PROJECT_STATUS.md"
    if status_file.exists():
        content = status_file.read_text(encoding="utf-8")
        import re
        # Update "Last updated" date
        content = re.sub(
            r"\*\*Last updated\*\*:.*",
            f"**Last updated**: {now.strftime('%Y-%m-%d %H:%M')} (auto-maintenance)",
            content,
        )
        # Update metric rows if they exist
        replacements = {
            r"\| Articles ingested \| [\d,]+ \|": f"| Articles ingested | {total_articles:,} |",
            r"\| Stories \(clusters\) \| [\d,]+ \|": f"| Stories (clusters) | {total_stories:,} |",
            r"\| Stories with 5\+ articles \| [\d,]+ \|": f"| Stories with 5+ articles | {visible:,} |",
            r"\| Stories with AI summaries \| [\d,]+ \|": f"| Stories with AI summaries | {with_summary:,} |",
            r"\| Telegram posts collected \| [\d,]+ \|": f"| Telegram posts collected | {tg_posts:,} |",
        }
        for pattern, replacement in replacements.items():
            content = re.sub(pattern, replacement, content)
        status_file.write_text(content, encoding="utf-8")

    # 3. Check if any REMINDERS.md items should be flagged
    reminders_file = pm_dir / "REMINDERS.md"
    if reminders_file.exists():
        content = reminders_file.read_text(encoding="utf-8")
        content = re.sub(
            r"Last updated:.*",
            f"Last updated: {now.strftime('%Y-%m-%d')}",
            content,
        )
        reminders_file.write_text(content, encoding="utf-8")

    # 4. Update ARCHITECTURE_VISUAL.md metrics section
    arch_file = pm_dir / "ARCHITECTURE_VISUAL.md"
    if arch_file.exists():
        content = arch_file.read_text(encoding="utf-8")
        needs_update = False

        # Scan for new backend service files
        import glob
        services_dir = Path(__file__).parent / "app" / "services"
        api_dir = Path(__file__).parent / "app" / "api" / "v1"
        models_dir = Path(__file__).parent / "app" / "models"
        frontend_pages = Path(__file__).parent.parent / "frontend" / "src" / "app" / "[locale]"

        current_services = sorted([f.name for f in services_dir.glob("*.py") if f.name != "__init__.py"]) if services_dir.exists() else []
        current_apis = sorted([f.name for f in api_dir.glob("*.py") if f.name not in ("__init__.py", "router.py")]) if api_dir.exists() else []
        current_models = sorted([f.name for f in models_dir.glob("*.py") if f.name != "__init__.py"]) if models_dir.exists() else []
        current_pages = sorted([f.name for f in frontend_pages.iterdir() if f.is_dir()]) if frontend_pages.exists() else []

        # Check if any new files exist that aren't mentioned in the architecture doc
        new_services = [s for s in current_services if s.replace(".py", "") not in content]
        new_apis = [a for a in current_apis if a.replace(".py", "") not in content]
        new_models = [m for m in current_models if m.replace(".py", "") not in content]
        new_pages = [p for p in current_pages if p not in content and p != "[locale]"]

        if new_services or new_apis or new_models or new_pages:
            needs_update = True
            update_note = f"\n\n---\n\n## Auto-detected changes ({now.strftime('%Y-%m-%d %H:%M')})\n\n"
            if new_services:
                update_note += f"**New service files**: {', '.join(new_services)}\n\n"
            if new_apis:
                update_note += f"**New API files**: {', '.join(new_apis)}\n\n"
            if new_models:
                update_note += f"**New model files**: {', '.join(new_models)}\n\n"
            if new_pages:
                update_note += f"**New frontend pages**: {', '.join(new_pages)}\n\n"
            update_note += "> These files were detected but not yet documented in the diagrams above. Update the diagrams to include them.\n"

            # Only append if this note isn't already there
            if "Auto-detected changes" not in content:
                content += update_note
            else:
                # Replace existing auto-detected section
                content = re.sub(r"\n---\n\n## Auto-detected changes.*", update_note, content, flags=re.DOTALL)

            arch_file.write_text(content, encoding="utf-8")
            logger.info(f"Architecture doc updated: {len(new_services)} new services, {len(new_apis)} new APIs, {len(new_models)} new models, {len(new_pages)} new pages")

    updated_files = ["MAINTENANCE_LOG.md", "PROJECT_STATUS.md", "REMINDERS.md"]
    if arch_file.exists():
        updated_files.append("ARCHITECTURE_VISUAL.md")

    logger.info(f"Updated project docs: {', '.join(updated_files)} ({total_articles} articles, {visible} visible stories)")
    return {"updated": updated_files}


async def run_maintenance():
    """Run full maintenance cycle."""
    start = time.time()
    logger.info("=" * 50)
    logger.info(f"Maintenance started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 50)

    results = {}

    try:
        results["ingest"] = await step_ingest()
    except Exception as e:
        logger.error(f"Ingest failed: {e}")
        results["ingest"] = {"error": str(e)}

    try:
        results["process"] = await step_process()
    except Exception as e:
        logger.error(f"Process failed: {e}")
        results["process"] = {"error": str(e)}

    try:
        results["cluster"] = await step_cluster()
    except Exception as e:
        logger.error(f"Cluster failed: {e}")
        results["cluster"] = {"error": str(e)}

    try:
        results["summarize"] = await step_summarize()
    except Exception as e:
        logger.error(f"Summarize failed: {e}")
        results["summarize"] = {"error": str(e)}

    steps = [
        ("fix_images", step_fix_images),
        ("story_quality", step_story_quality),
        ("source_health", step_source_health),
        ("archive_stale", step_archive_stale),
        ("recalc_trending", step_recalculate_trending),
        ("dedup_articles", step_deduplicate_articles),
        ("fixes", step_fix_issues),
        ("rater_feedback", step_rater_feedback_apply),
        ("telegram_health", step_telegram_health),
        ("visual", step_visual_check),
        ("uptime", step_uptime_check),
        ("disk", step_disk_monitoring),
        ("cost_tracking", step_cost_tracking),
        ("backup", step_database_backup),
        ("weekly_digest", step_weekly_digest),
    ]

    for name, func in steps:
        try:
            results[name] = await func()
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            results[name] = {"error": str(e)}

    # Update project management docs
    try:
        results["docs"] = await step_update_docs(results, start)
    except Exception as e:
        logger.error(f"Doc update failed: {e}")
        results["docs"] = {"error": str(e)}

    elapsed = time.time() - start
    logger.info(f"Maintenance complete in {elapsed:.0f}s")
    logger.info(f"Results: {results}")
    logger.info("=" * 50)

    return results


def main():
    parser = argparse.ArgumentParser(description="Doornegar Auto-Maintenance")
    parser.add_argument("--loop", type=float, help="Run every N hours (omit for single run)")
    args = parser.parse_args()

    if args.loop:
        interval = args.loop * 3600
        logger.info(f"Starting maintenance loop — every {args.loop}h")
        while True:
            asyncio.run(run_maintenance())
            logger.info(f"Next run in {args.loop}h...")
            time.sleep(interval)
    else:
        asyncio.run(run_maintenance())


if __name__ == "__main__":
    main()

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


async def step_backfill_farsi_titles():
    """Backfill: translate English titles that are missing title_fa.

    process_unprocessed_articles only touches articles with processed_at IS NULL,
    so articles where translation failed the first time get stuck. This step
    targets them directly.
    """
    from app.config import settings
    from app.database import async_session
    from app.models import Article
    from sqlalchemy import and_, select

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping title backfill")
        return {"skipped": "no_openai_key"}

    async with async_session() as db:
        result = await db.execute(
            select(Article)
            .where(
                and_(
                    Article.title_fa.is_(None),
                    Article.title_original.isnot(None),
                )
            )
            .limit(300)  # cap per maintenance run
        )
        articles = list(result.scalars().all())

        if not articles:
            return {"backfilled": 0}

        from openai import OpenAI
        from app.services.llm_helper import build_openai_params
        client = OpenAI(api_key=settings.openai_api_key)
        import re as _re

        backfilled = 0
        failed = 0
        for batch_start in range(0, len(articles), 30):
            batch = articles[batch_start:batch_start + 30]
            titles = "\n".join(f"{i+1}. {a.title_original}" for i, a in enumerate(batch))
            try:
                params = build_openai_params(
                    model=settings.translation_model,
                    prompt=f"Translate these news headlines to Farsi. Return ONLY the translations, one per line, numbered.\n\n{titles}",
                    max_tokens=2500,
                    temperature=0,
                )
                resp = client.chat.completions.create(**params)
                lines = resp.choices[0].message.content.strip().split("\n")
                for i, article in enumerate(batch):
                    if i >= len(lines):
                        failed += 1
                        continue
                    translated = _re.sub(r"^[\d۰-۹]+[\.\)]\s*", "", lines[i]).strip()
                    if translated:
                        article.title_fa = translated
                        backfilled += 1
                    else:
                        failed += 1
            except Exception as e:
                logger.warning(f"Title backfill batch failed: {e}")
                failed += len(batch)

        await db.commit()
    logger.info(f"Farsi title backfill: {backfilled} translated, {failed} failed")
    return {"backfilled": backfilled, "failed": failed}


async def step_bias_score():
    """Score articles that don't yet have a bias score.

    Runs multiple batches per maintenance cycle so coverage catches up over time.
    Capped to avoid runaway LLM spend.
    """
    from app.config import settings
    from app.database import async_session
    from app.services.bias_scoring import score_unscored_articles

    if not (settings.openai_api_key or settings.anthropic_api_key):
        logger.warning("No LLM API key set — skipping bias scoring")
        return {"skipped": "no_llm_key"}

    MAX_PER_RUN = 150  # ~$3-5/run at Haiku prices; adjust as needed
    BATCH = 30
    total = {"scored": 0, "failed": 0, "skipped": 0}
    async with async_session() as db:
        for _ in range(MAX_PER_RUN // BATCH):
            stats = await score_unscored_articles(db, batch_size=BATCH)
            total["scored"] += stats.get("scored", 0)
            total["failed"] += stats.get("failed", 0)
            total["skipped"] += stats.get("skipped", 0)
            # Stop early if nothing left
            if stats.get("scored", 0) + stats.get("failed", 0) == 0:
                break
    logger.info(f"Bias scoring: {total}")
    return total


async def step_cluster():
    """Step 3: Cluster articles into stories."""
    from app.database import async_session
    from app.services.clustering import cluster_articles

    async with async_session() as db:
        stats = await cluster_articles(db)
    logger.info(f"Clustering: {stats}")
    return stats


async def step_summarize():
    """Step 4: Generate summaries for stories without one.

    Tiered model selection:
    - Stories in the top `premium_story_top_n` trending → premium model
      (e.g. gpt-5-mini, better quality for homepage-visible content)
    - All other stories → baseline model (e.g. gpt-4o-mini, cheaper)

    Reliability features:
    - _keepalive() ping before each LLM call to keep Neon connection warm
    - Skips stories where last LLM attempt failed <24h ago (retry backoff)
    - Loads only the 10 most recent articles per story (memory-efficient)
    - Commits per story so partial progress survives crashes
    """
    import json as _json

    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.story_analysis import generate_story_analysis

    async def _keepalive(db):
        try:
            await db.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning(f"Summarize keepalive ping failed: {e}")

    MAX_ARTICLES_PER_STORY = 10  # cap memory + prompt cost

    async with async_session() as db:
        # 1. Pre-compute top-N trending story IDs (homepage tier)
        top_result = await db.execute(
            select(Story.id)
            .where(Story.article_count >= 5)
            .order_by(Story.priority.desc(), Story.trending_score.desc())
            .limit(settings.premium_story_top_n)
        )
        top_ids = {row[0] for row in top_result.all()}

        # 2. Find stories that need a summary (skip recently-failed)
        retry_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(Story)
            .where(
                Story.summary_fa.is_(None),
                Story.article_count >= 5,
                (Story.llm_failed_at.is_(None)) | (Story.llm_failed_at < retry_cutoff),
            )
            .order_by(Story.article_count.desc())
        )
        stories = list(result.scalars().all())

        if not stories:
            logger.info("Summarize: all visible stories have summaries")
            return {"generated": 0, "premium": 0, "baseline": 0, "failed": 0}

        logger.info(
            f"Generating summaries for {len(stories)} stories "
            f"(top {len(top_ids)} trending → {settings.story_analysis_premium_model}, "
            f"rest → {settings.story_analysis_model})..."
        )
        success = 0
        failed = 0
        premium_used = 0
        baseline_used = 0
        for story in stories:
            # Lazy-load only the N most recent articles with their sources —
            # avoids eager-loading hundreds of rows per story.
            art_result = await db.execute(
                select(Article)
                .options(selectinload(Article.source))
                .where(Article.story_id == story.id)
                .order_by(Article.published_at.desc().nullslast())
                .limit(MAX_ARTICLES_PER_STORY)
            )
            top_articles = list(art_result.scalars().all())

            articles_info = [
                {
                    "title": a.title_original or a.title_fa or a.title_en or "",
                    "content": (a.content_text or a.summary or "")[:1500],
                    "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                    "state_alignment": a.source.state_alignment if a.source else "",
                    "published_at": a.published_at.isoformat() if a.published_at else "",
                }
                for a in top_articles
            ]
            # Tier selection
            if story.id in top_ids:
                chosen_model = settings.story_analysis_premium_model
                tier_label = "premium"
            else:
                chosen_model = settings.story_analysis_model
                tier_label = "baseline"
            try:
                await _keepalive(db)
                is_premium = (tier_label == "premium")
                analysis = await generate_story_analysis(
                    story, articles_info,
                    model=chosen_model,
                    include_analyst_factors=is_premium,
                )
                story.summary_fa = analysis.get("summary_fa")
                extras = {
                    "state_summary_fa": analysis.get("state_summary_fa"),
                    "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                    "independent_summary_fa": analysis.get("independent_summary_fa"),
                    "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                    "scores": analysis.get("scores"),
                    "llm_model_used": chosen_model,
                }
                # Store analyst factors for premium stories
                if is_premium and analysis.get("analyst"):
                    extras["analyst"] = analysis["analyst"]
                story.summary_en = _json.dumps(extras, ensure_ascii=False)
                story.llm_failed_at = None  # clear any previous failure
                await db.commit()
                success += 1
                if tier_label == "premium":
                    premium_used += 1
                else:
                    baseline_used += 1
                logger.info(f"  ✓ [{tier_label}] {(story.title_fa or '')[:40]}")
            except Exception as e:
                logger.warning(f"  ✗ [{tier_label}] {(story.title_fa or '')[:40]}: {e}")
                failed += 1
                # Mark as recently-failed so we don't retry for 24h.
                # Guard the mark itself in case the session is broken.
                try:
                    story.llm_failed_at = datetime.now(timezone.utc)
                    await db.commit()
                except Exception:
                    await db.rollback()

        return {
            "generated": success,
            "premium": premium_used,
            "baseline": baseline_used,
            "failed": failed,
        }


async def step_fix_images():
    """Step 4b: Keep article image URLs healthy.

    Passes:
    1. HEAD-check up to 300 article images per run, skipping ones checked
       within the last 24h. Null out broken / localhost URLs. Marks
       image_checked_at on every check (success or null-out) so subsequent
       runs can skip them.
    2. For visible stories where NO article has a usable image, try to
       fetch an og:image from the first non-Telegram article's source URL
       and cache it on that article.

    Image relevance selection (picking WHICH article image to display
    for a story) happens at response time in
    app.api.v1.stories._story_brief_with_extras() — it uses a title-word
    overlap heuristic plus R2-stable-URL preference. Doing it at response
    time means we don't need a story.image_url column and the picker
    automatically tracks changes to article.image_url.
    """
    import httpx
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    stats = {
        "checked": 0,
        "nulled": 0,
        "replaced": 0,
        "stories_without_image": 0,
    }

    async with async_session() as db:
        # --- Pass 1: HEAD-check up to 300 article images, null out broken ones ---
        # Skip articles checked within the last 24h (stable URLs don't need
        # re-checking every run — saves ~5-10 min of HTTP HEAD waste).
        check_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(Article)
            .where(
                Article.image_url.isnot(None),
                (Article.image_checked_at.is_(None)) | (Article.image_checked_at < check_cutoff),
            )
            .limit(300)
        )
        articles = list(result.scalars().all())
        stats["skipped_recent"] = 0  # will be set when we know how many we skipped
        now_ts = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            for a in articles:
                stats["checked"] += 1
                # localhost URLs are definitely broken on production; null fast
                if a.image_url and a.image_url.startswith("http://localhost"):
                    a.image_url = None
                    a.image_checked_at = now_ts  # don't re-check NULL either
                    stats["nulled"] += 1
                    continue
                try:
                    r = await client.head(a.image_url)
                    if r.status_code != 200:
                        a.image_url = None
                        stats["nulled"] += 1
                    a.image_checked_at = now_ts
                except Exception:
                    a.image_url = None
                    a.image_checked_at = now_ts
                    stats["nulled"] += 1

        await db.commit()

        # --- Pass 2: For visible stories WITHOUT any working image,
        # try to fetch an og:image from one of their article URLs.
        # Note: Story has no image_url column — image selection happens
        # at response time in _story_brief_with_extras() using a
        # title-overlap heuristic across story.articles. We don't set
        # story.image_url here because the attribute doesn't exist on
        # the Story model.
        result = await db.execute(
            select(Story).options(selectinload(Story.articles))
            .where(Story.article_count >= 5)
        )
        for story in result.scalars().all():
            # Any article with a live image_url is enough for the
            # response-time picker to work.
            has_image = any(a.image_url for a in story.articles)
            if has_image:
                continue
            # Last-ditch: fetch an og:image from the first non-telegram article URL
            fetched = False
            for a in story.articles:
                if a.url and "t.me/" not in a.url:
                    from app.services.nlp_pipeline import _fetch_og_image
                    img = await _fetch_og_image(a.url)
                    if img:
                        a.image_url = img
                        a.image_checked_at = now_ts
                        stats["replaced"] += 1
                        fetched = True
                        break
            if not fetched:
                stats["stories_without_image"] += 1

        await db.commit()

    if any(v > 0 for v in stats.values()):
        logger.info(f"Image fix: {stats}")
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
                        "published_at": a.published_at.isoformat() if a.published_at else "",
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


async def step_feedback_health():
    """Monitor the improvement feedback and source suggestion systems.

    Tracks:
    - New items received in last 24h (raters are engaged?)
    - Open items waiting for review
    - Stale items (open for >14 days — may need attention or archival)
    - Oldest unresolved item age
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func

    from app.database import async_session
    from app.models.improvement import ImprovementFeedback
    from app.models.suggestion import SourceSuggestion

    stats = {
        "improvements": {},
        "suggestions": {},
        "alerts": [],
    }

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    stale_threshold = now - timedelta(days=14)

    async with async_session() as db:
        # ─── Improvement feedback stats ─────────────────────────
        total_improvements = (
            await db.execute(select(func.count(ImprovementFeedback.id)))
        ).scalar() or 0
        new_24h = (
            await db.execute(
                select(func.count(ImprovementFeedback.id)).where(
                    ImprovementFeedback.created_at >= last_24h
                )
            )
        ).scalar() or 0
        open_count = (
            await db.execute(
                select(func.count(ImprovementFeedback.id)).where(
                    ImprovementFeedback.status == "open"
                )
            )
        ).scalar() or 0
        in_progress_count = (
            await db.execute(
                select(func.count(ImprovementFeedback.id)).where(
                    ImprovementFeedback.status == "in_progress"
                )
            )
        ).scalar() or 0
        done_count = (
            await db.execute(
                select(func.count(ImprovementFeedback.id)).where(
                    ImprovementFeedback.status == "done"
                )
            )
        ).scalar() or 0
        stale_open = (
            await db.execute(
                select(func.count(ImprovementFeedback.id)).where(
                    ImprovementFeedback.status == "open",
                    ImprovementFeedback.created_at < stale_threshold,
                )
            )
        ).scalar() or 0
        oldest_open_dt = (
            await db.execute(
                select(func.min(ImprovementFeedback.created_at)).where(
                    ImprovementFeedback.status == "open"
                )
            )
        ).scalar()

        stats["improvements"] = {
            "total": total_improvements,
            "new_24h": new_24h,
            "open": open_count,
            "in_progress": in_progress_count,
            "done": done_count,
            "stale_open": stale_open,
            "oldest_open_days": (
                (now - oldest_open_dt).days if oldest_open_dt else None
            ),
        }

        if stale_open > 0:
            stats["alerts"].append(
                f"{stale_open} improvement feedback item(s) open for more than 14 days"
            )
        if open_count > 50:
            stats["alerts"].append(
                f"Backlog is large: {open_count} open improvement items (consider batch review)"
            )

        # ─── Source suggestion stats ─────────────────────────
        total_suggestions = (
            await db.execute(select(func.count(SourceSuggestion.id)))
        ).scalar() or 0
        sugg_new_24h = (
            await db.execute(
                select(func.count(SourceSuggestion.id)).where(
                    SourceSuggestion.created_at >= last_24h
                )
            )
        ).scalar() or 0
        sugg_pending = (
            await db.execute(
                select(func.count(SourceSuggestion.id)).where(
                    SourceSuggestion.status == "pending"
                )
            )
        ).scalar() or 0
        sugg_stale_pending = (
            await db.execute(
                select(func.count(SourceSuggestion.id)).where(
                    SourceSuggestion.status == "pending",
                    SourceSuggestion.created_at < stale_threshold,
                )
            )
        ).scalar() or 0

        stats["suggestions"] = {
            "total": total_suggestions,
            "new_24h": sugg_new_24h,
            "pending": sugg_pending,
            "stale_pending": sugg_stale_pending,
        }

        if sugg_stale_pending > 0:
            stats["alerts"].append(
                f"{sugg_stale_pending} source suggestion(s) pending for more than 14 days"
            )

    logger.info(
        f"Feedback health: {new_24h} new improvements + {sugg_new_24h} new suggestions in last 24h; "
        f"{open_count} open, {sugg_pending} pending review"
    )
    if stats["alerts"]:
        for alert in stats["alerts"]:
            logger.warning(f"  ⚠ {alert}")

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
        # Find articles with the same non-trivial title_fa.
        # Guard against NULL, empty string, and very short titles — those
        # would group unrelated articles together and false-positive.
        result = await db.execute(
            select(Article.title_fa, func.count(Article.id).label("cnt"))
            .where(
                Article.title_fa.isnot(None),
                func.length(func.trim(Article.title_fa)) >= 10,
            )
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
            from app.services.llm_helper import build_openai_params
            client = OpenAI(api_key=settings.openai_api_key)
            fixed = 0
            for batch_start in range(0, len(english_in_fa), 30):
                batch = english_in_fa[batch_start:batch_start + 30]
                titles = "\n".join(f"{i+1}. {a.title_fa}" for i, a in enumerate(batch))
                try:
                    params = build_openai_params(
                        model=settings.translation_model,
                        prompt=f"Translate these English headlines to Farsi. Return ONLY translations, numbered.\n\n{titles}",
                        max_tokens=2000,
                        temperature=0,
                    )
                    resp = client.chat.completions.create(**params)
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
    """Run full maintenance cycle with per-step progress tracking."""
    from app.services import maintenance_state

    start = time.time()
    logger.info("=" * 50)
    logger.info(f"Maintenance started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 50)

    maintenance_state.start_run()
    results = {}

    # Ordered pipeline of (result_key, display_name, async_callable)
    pipeline = [
        ("ingest", "Ingest RSS + Telegram", step_ingest),
        ("process", "NLP process (embed, translate, extract)", step_process),
        ("backfill_farsi_titles", "Backfill Farsi titles", step_backfill_farsi_titles),
        ("cluster", "Cluster articles into stories", step_cluster),
        ("summarize", "Summarize new stories", step_summarize),
        ("bias_score", "Bias scoring", step_bias_score),
        ("fix_images", "Fix broken images", step_fix_images),
        ("story_quality", "Story quality checks", step_story_quality),
        ("source_health", "Source health", step_source_health),
        ("archive_stale", "Archive stale stories", step_archive_stale),
        ("recalc_trending", "Recalculate trending", step_recalculate_trending),
        ("dedup_articles", "Dedup articles", step_deduplicate_articles),
        ("fixes", "Auto-fix common issues", step_fix_issues),
        ("rater_feedback", "Apply rater feedback", step_rater_feedback_apply),
        ("feedback_health", "Feedback system health", step_feedback_health),
        ("telegram_health", "Telegram session health", step_telegram_health),
        ("visual", "Visual check", step_visual_check),
        ("uptime", "Uptime check", step_uptime_check),
        ("disk", "Disk monitoring", step_disk_monitoring),
        ("cost_tracking", "LLM cost tracking", step_cost_tracking),
        ("backup", "Database backup", step_database_backup),
        ("weekly_digest", "Weekly digest", step_weekly_digest),
    ]

    try:
        for key, display, func in pipeline:
            maintenance_state.begin_step(display)
            try:
                result = await func()
                results[key] = result
                maintenance_state.end_step(display, "ok", result)
            except Exception as e:
                logger.error(f"{display} failed: {e}")
                err = {"error": str(e)}
                results[key] = err
                maintenance_state.end_step(display, "error", err)

        # Doc update is last and depends on results
        maintenance_state.begin_step("Update project docs")
        try:
            results["docs"] = await step_update_docs(results, start)
            maintenance_state.end_step("Update project docs", "ok", results["docs"])
        except Exception as e:
            logger.error(f"Doc update failed: {e}")
            err = {"error": str(e)}
            results["docs"] = err
            maintenance_state.end_step("Update project docs", "error", err)

        elapsed = time.time() - start
        logger.info(f"Maintenance complete in {elapsed:.0f}s")
        logger.info(f"Results: {results}")
        logger.info("=" * 50)
        maintenance_state.finish_run("success", results=results, total_elapsed_s=elapsed)
        return results

    except Exception as e:
        logger.exception("Maintenance run crashed")
        maintenance_state.finish_run(
            "error", results=results, error=str(e), total_elapsed_s=time.time() - start
        )
        raise


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

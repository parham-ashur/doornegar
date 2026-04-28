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
  python auto_maintenance.py                  # Run once, full pipeline
  python auto_maintenance.py --loop 4         # Run every 4 hours
  python auto_maintenance.py --mode ingest    # Ingest + NLP + cluster only (lightweight)
"""

import argparse
import asyncio
import logging
import re
import sys
import time
import uuid
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


# ──────────────────────────────────────────────────────────────────────
# Per-step timeouts (seconds). Anything not listed uses DEFAULT_STEP_TIMEOUT.
# A step that blows past its budget is cancelled; the rest of the pipeline
# continues. Tune by watching the maintenance log for TimeoutError.
# ──────────────────────────────────────────────────────────────────────
DEFAULT_STEP_TIMEOUT_SEC = 900  # 15 min — applies to the ~25 light steps
STEP_TIMEOUTS_SEC = {
    "ingest": 1800,                # RSS + Telegram for 20+ sources
    "ingest_rss": 900,             # RSS only — hourly mode, stricter budget
    "prune_noise": 180,            # single UPDATE/DELETE batch, no LLM
    "recount": 60,                 # two UPDATE…FROM (GROUP BY) queries, no LLM
    "classify_content_type": 600,  # heuristic + small LLM batches, capped per run
    "detect_hourly_updates": 120,  # pure SQL aggregate, no LLM
    "audit_clusters": 300,         # sample + cosine, no LLM
    "process": 1800,               # embeddings + translation over many articles
    "cluster": 1200,               # LLM clustering batch
    "centroids": 600,
    "merge_similar": 600,
    "summarize": 1800,
    "bias_score": 3600,            # per-article LLM calls, heaviest step
    "fix_images": 1200,
    "diaspora_ogimages": 1200,   # HTTP GET per article, capped 200/run
    "migrate_images_r2": 1800,   # download + upload per article, capped 300/run
    "telegram_analysis": 3600,     # per-story LLM analysis
    "telegram_reassign": 1200,     # re-embed 3K posts, pure math, no LLM
    "niloofar_image_rescue": 300,  # no LLM — scans article images, picks fallback
    "backfill_analyst_counts": 300,  # no LLM — just resolves supporter names
    "editorial": 1200,
    "niloofar_polish_telegram": 900,
    "quality_postprocess": 1800,
    "weekly_digest": 900,
    "worldview_digests": 600,      # 4 LLM calls, compact input, weekly
}


# ──────────────────────────────────────────────────────────────────────
# Cron coordination
# ──────────────────────────────────────────────────────────────────────
# Primary defense: schedule deconfliction. The three Railway cron
# services are scheduled to never fire at the same minute:
#
#   maintenance-cron   0 4 * * *                      (full, daily)
#   ingest-cron        0 */6 * * *                    (6h, 00/06/12/18 UTC)
#   rss-cron           0 5,7-11,13-17,19-21 * * *     (hourly, skips
#                                                      04/06/12/18 UTC)
#
# Any new cron MUST avoid these 4 slots or the three existing ones will
# need to be restaggered.
#
# Concurrency guard: postgres-table lock (Redis isn't deployed in this
# project, so the previous Redis-based lock failed open and let two
# maintenance runs race each other — confirmed by the 2026-04-27 incident
# where a manual dashboard run overlapped a scheduled cron and produced a
# 10h+ run with connection-drop and FK errors). Self-heals via a stale
# threshold so a crashed holder can't lock the system out forever.
LOCK_KEY_INT = 7263482917      # arbitrary unique key for this lock row
LOCK_STALE_SEC = 4 * 3600      # 4 hours — any older than this and we override


def try_acquire_lock(label: str) -> bool:
    """Try to acquire the maintenance lock. Returns True on success.
    The lock is a single row in `maintenance_lock`; INSERT...ON CONFLICT
    DO NOTHING gives us atomic test-and-set semantics in one round trip.
    A stale lock (older than LOCK_STALE_SEC) is forced-overridden so a
    process that died mid-run doesn't permanently block the system.
    """
    import psycopg2  # noqa: F401  (sync driver — fine for this small probe)
    from app.config import settings as _settings
    from sqlalchemy import create_engine, text as _t

    sync_url = (_settings.database_url or "").replace("+asyncpg", "")
    if not sync_url:
        logger.warning("DATABASE_URL unset — proceeding without lock")
        return True
    try:
        eng = create_engine(sync_url, pool_pre_ping=True)
        with eng.begin() as conn:
            # Self-heal: clear stale locks before we try to take ours.
            conn.execute(_t(
                "DELETE FROM maintenance_lock "
                "WHERE id = :k AND acquired_at < NOW() - (:s || ' seconds')::interval"
            ), {"k": LOCK_KEY_INT, "s": LOCK_STALE_SEC})
            result = conn.execute(_t(
                "INSERT INTO maintenance_lock (id, label, acquired_at) "
                "VALUES (:k, :label, NOW()) ON CONFLICT (id) DO NOTHING"
            ), {"k": LOCK_KEY_INT, "label": label})
            return (result.rowcount or 0) > 0
    except Exception as e:
        logger.warning(
            "Could not check maintenance lock: %s — proceeding without lock", e
        )
        return True


def release_lock() -> None:
    """Drop the maintenance lock row. Safe if it's already gone."""
    from app.config import settings as _settings
    from sqlalchemy import create_engine, text as _t

    sync_url = (_settings.database_url or "").replace("+asyncpg", "")
    if not sync_url:
        return
    try:
        eng = create_engine(sync_url, pool_pre_ping=True)
        with eng.begin() as conn:
            conn.execute(_t("DELETE FROM maintenance_lock WHERE id = :k"),
                         {"k": LOCK_KEY_INT})
    except Exception as e:
        logger.warning("Could not release maintenance lock: %s", e)


async def step_ingest():
    """Step 1: Fetch new articles from RSS + Telegram."""
    from app.database import async_session
    from app.services.ingestion import ingest_all_sources
    from app.services.telegram_service import (
        convert_telegram_posts_to_articles,
        extract_articles_from_aggregators,
        ingest_all_channels,
    )

    async with async_session() as db:
        # Seed any new RSS sources from seed.py that aren't in the DB yet.
        # Idempotent — existing slugs are skipped. Lets a new source land via
        # `git push` without requiring a manual `python manage.py seed`.
        from app.services.seed import seed_sources
        new_sources = await seed_sources(db)
        if new_sources:
            logger.info(f"Seeded {new_sources} new RSS sources from seed.py")

        # Seed any new Telegram channels
        from app.services.seed_telegram import seed_telegram_channels
        seeded = await seed_telegram_channels(db)
        if seeded:
            logger.info(f"Seeded {seeded} new Telegram channels")

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

        # Extract articles from aggregator channel links
        logger.info("Extracting articles from aggregator channels...")
        aggregator_stats = await extract_articles_from_aggregators(db)
        logger.info(f"Aggregator extraction: {aggregator_stats}")

    return {
        "rss_new": rss_stats.get("new", 0),
        "telegram_new": tg_stats.get("new", 0),
        "converted": convert_stats.get("created", 0),
        "aggregator_articles": aggregator_stats.get("articles_created", 0),
    }


async def step_ingest_rss():
    """RSS-only ingest. Used by the hourly cron so we refresh news coverage
    fast without paying for Telegram polling (which is the slow part of
    the full ingest step).

    Does NOT touch telegram_channels, telegram_posts, aggregators, or the
    telegram→article conversion. Those stay in the 6h ingest-cron.
    """
    from app.database import async_session
    from app.services.ingestion import ingest_all_sources
    from app.services.seed import seed_sources

    async with async_session() as db:
        new_sources = await seed_sources(db)
        if new_sources:
            logger.info(f"Seeded {new_sources} new RSS sources from seed.py")

        logger.info("Ingesting RSS feeds (hourly mode)...")
        rss_stats = await ingest_all_sources(db)
        logger.info(f"RSS: {rss_stats}")

    return {"rss_new": rss_stats.get("new", 0)}


async def step_detect_hourly_updates():
    """Deterministic per-story update detection for the hourly cron.

    Runs after step_cluster + step_recompute_centroids. For every story
    that gained articles in the last hour, compare the source-side
    distribution "before the hour" vs "now". Writes story.hourly_update_signal
    when any of these triggers fire:

      - Side flip: story was state-only, first diaspora article arrived
        (or vice versa). Strongest signal — a whole half of the coverage
        just joined.
      - Coverage shift: state/diaspora ratio moved ≥ 15pp in an hour.
        "پوشش درون‌مرزی تقویت شد (۴۰٪ → ۵۵٪)"
      - Burst: ≥2 articles attached to one story within the hour. Small
        drip on a quiet story still signals movement worth surfacing.

    Stories that gained articles but tripped no trigger get
    hourly_update_signal = {"has_update": False, ...} — the API then
    falls back to the 24h snapshot signal for the badge. Either way,
    Story.last_updated_at is already ticked by the article-cluster step,
    so the "updated X minutes ago" timestamp stays accurate.

    Pure SQL aggregates, no LLM, ~<2s on the full stories table.
    """
    from sqlalchemy import text as _text

    from app.database import async_session

    # Minimum delta used for the coverage-shift trigger. Matches the 24h
    # snapshot's threshold so the two signal layers stay consistent.
    PCT_SHIFT = 15
    BURST_ARTICLES = 2

    stats = {"stories_seen": 0, "side_flip": 0, "coverage_shift": 0, "burst": 0, "quiet": 0}

    # Single aggregate query: every story that gained at least one article
    # in the last hour, with state/diaspora counts before vs after.
    # `state_alignment` values: state, semi_state, independent, diaspora.
    # We collapse into two buckets — inside (state+semi_state) and
    # outside (diaspora+independent) — same as the coverage bar does.
    sql = _text("""
        WITH touched AS (
            SELECT DISTINCT story_id
            FROM articles
            WHERE created_at >= NOW() - INTERVAL '1 hour'
              AND story_id IS NOT NULL
        )
        SELECT
            a.story_id,
            COUNT(*) FILTER (WHERE a.created_at >= NOW() - INTERVAL '1 hour') AS new_count,
            COUNT(*) FILTER (
                WHERE a.created_at < NOW() - INTERVAL '1 hour'
                  AND s.state_alignment IN ('state','semi_state')
            ) AS inside_before,
            COUNT(*) FILTER (
                WHERE a.created_at < NOW() - INTERVAL '1 hour'
                  AND s.state_alignment IN ('diaspora','independent')
            ) AS outside_before,
            COUNT(*) FILTER (WHERE s.state_alignment IN ('state','semi_state')) AS inside_after,
            COUNT(*) FILTER (WHERE s.state_alignment IN ('diaspora','independent')) AS outside_after
        FROM articles a
        JOIN sources s ON s.id = a.source_id
        WHERE a.story_id IN (SELECT story_id FROM touched)
        GROUP BY a.story_id
    """)

    now_iso = datetime.now(timezone.utc).isoformat()

    async with async_session() as db:
        rows = (await db.execute(sql)).all()
        stats["stories_seen"] = len(rows)

        for row in rows:
            story_id = row.story_id
            new_count = int(row.new_count or 0)
            inside_before = int(row.inside_before or 0)
            outside_before = int(row.outside_before or 0)
            inside_after = int(row.inside_after or 0)
            outside_after = int(row.outside_after or 0)
            total_before = inside_before + outside_before
            total_after = inside_after + outside_after

            signal = {"has_update": False, "kind": None, "reason_fa": None, "detected_at": now_iso}

            # Trigger 1: side flip. "Was state-only" means total_before > 0
            # and outside_before == 0, and now outside_after > 0.
            if total_before > 0 and outside_before == 0 and outside_after > 0:
                signal = {
                    "has_update": True, "kind": "side_flip",
                    "reason_fa": "رسانه‌های برون‌مرزی به پوشش پیوستند",
                    "detected_at": now_iso,
                }
                stats["side_flip"] += 1
            elif total_before > 0 and inside_before == 0 and inside_after > 0:
                signal = {
                    "has_update": True, "kind": "side_flip",
                    "reason_fa": "رسانه‌های درون‌مرزی به پوشش پیوستند",
                    "detected_at": now_iso,
                }
                stats["side_flip"] += 1
            # Trigger 2: coverage shift ≥ 15pp. Only evaluate when both
            # before and after have enough rows to compute a meaningful
            # percentage — a jump from 0 articles to 3 isn't a "shift".
            # Requires inside_before ≥ 1 AND outside_before ≥ 1 so we
            # don't claim a "shift" on a story that was one-sided an
            # hour ago (that's actually trigger 1's job).
            elif total_before >= 3 and total_after >= 3 and inside_before >= 1 and outside_before >= 1:
                pct_inside_before = round(100 * inside_before / total_before)
                pct_inside_after = round(100 * inside_after / total_after)
                delta = pct_inside_after - pct_inside_before
                if abs(delta) >= PCT_SHIFT:
                    # RTL-friendly "old ← new" arrow; Farsi digits.
                    if delta > 0:
                        reason = f"پوشش درون‌مرزی تقویت شد ({_fa_digits(pct_inside_before)}٪ ← {_fa_digits(pct_inside_after)}٪)"
                    else:
                        pct_outside_before = 100 - pct_inside_before
                        pct_outside_after = 100 - pct_inside_after
                        reason = f"پوشش برون‌مرزی تقویت شد ({_fa_digits(pct_outside_before)}٪ ← {_fa_digits(pct_outside_after)}٪)"
                    signal = {
                        "has_update": True, "kind": "coverage_shift",
                        "reason_fa": reason, "detected_at": now_iso,
                    }
                    stats["coverage_shift"] += 1
            # Trigger 3: burst. Only if no earlier trigger fired.
            # `new_count` is stored alongside the Farsi reason so the UI
            # can regenerate the text with an age-correct window (e.g.
            # "۲ مقاله جدید در ۳ ساعت گذشته" when rendered 2h after the
            # cron wrote the signal).
            if not signal["has_update"] and new_count >= BURST_ARTICLES:
                signal = {
                    "has_update": True, "kind": "burst",
                    "reason_fa": f"{_fa_digits(new_count)} مقاله جدید در ساعت گذشته",
                    "new_count": new_count,
                    "detected_at": now_iso,
                }
                stats["burst"] += 1
            if not signal["has_update"]:
                stats["quiet"] += 1

            await db.execute(
                _text("UPDATE stories SET hourly_update_signal = :sig WHERE id = :sid"),
                {"sig": _json_dumps(signal), "sid": story_id},
            )
        await db.commit()

    logger.info(f"Hourly updates: {stats}")
    return stats


# Tiny helper — JSON encode with ensure_ascii=False so Farsi lands readable
# in the JSONB column rather than \u-escaped.
def _json_dumps(obj):
    import json as _j
    return _j.dumps(obj, ensure_ascii=False)


# Latin → Persian digits (۰–۹). Used in all Farsi user-facing reason
# strings so numbers render the same as the rest of the UI.
_FA_DIGITS_TABLE = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa_digits(n) -> str:
    return str(n).translate(_FA_DIGITS_TABLE)


async def step_prune_noise():
    """Drop near-zero-value ingested rows before they hit any LLM.

    Runs right after step_ingest and before step_process. We delete posts
    and telegram-originated articles that are so short they'll never
    contribute useful signal — single-word reactions, emoji-only posts,
    URL-only forwards — instead of paying to embed/translate/cluster
    them. NLP (`step_process`) embeds every unprocessed article, so even
    a 3-character "👍" pays for the call; trimming here saves tokens
    and shortens the downstream pipeline.

    Only targets rows that have not yet been analyzed downstream:
    - telegram_posts where sentiment_score IS NULL and story_id IS NULL
      (so we don't nuke a post that already got linked to a story).
    - articles where embedding IS NULL AND source is a Telegram channel
      and the text is below the same threshold. RSS articles are never
      short enough to trip this.

    Thresholds are conservative on purpose: something "like a tweet"
    (roughly ≥5 whitespace tokens and ≥30 chars after URL-stripping) is
    kept. Tune by editing MIN_TOKENS / MIN_CHARS / KEEP_IF_URLS below.
    """
    import re as _re
    from sqlalchemy import delete, select, text as _text

    from app.database import async_session
    from app.models.article import Article
    from app.models.social import TelegramPost

    # Tunable thresholds ────────────────────────────────────────────
    MIN_TOKENS = 5            # whitespace-separated tokens after URL strip
    MIN_CHARS = 30            # character count after URL + whitespace strip
    KEEP_IF_URLS = True       # keep URL-only posts if they carry ≥1 URL
    #                           (matters for aggregator channels whose job
    #                            is to forward news links)
    # ───────────────────────────────────────────────────────────────

    url_re = _re.compile(r"https?://\S+")

    def is_noise(text_val: str | None, urls: list | None) -> bool:
        if not text_val:
            return True
        stripped = url_re.sub(" ", text_val).strip()
        tokens = [t for t in stripped.split() if t]
        if len(tokens) >= MIN_TOKENS and len(stripped) >= MIN_CHARS:
            return False
        # Short. Last chance: aggregator-style "link only with label".
        if KEEP_IF_URLS and urls:
            return False
        return True

    stats = {"tg_checked": 0, "tg_deleted": 0, "articles_checked": 0, "articles_deleted": 0}

    async def _delete_articles_safe(db, ids: list) -> int:
        """Delete articles, skipping any with FK references in dependent
        tables (bias_scores / topics / ratings / feedback). Without this
        guard the DELETE raises ForeignKeyViolationError and rolls back
        the whole step. Articles that have been touched downstream aren't
        "near-zero-value" anymore — preserving them is intentional.
        """
        if not ids:
            return 0
        result = await db.execute(_text("""
            DELETE FROM articles
            WHERE id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM bias_scores       WHERE article_id = articles.id)
              AND NOT EXISTS (SELECT 1 FROM topic_articles    WHERE article_id = articles.id)
              AND NOT EXISTS (SELECT 1 FROM community_ratings WHERE article_id = articles.id)
              AND NOT EXISTS (SELECT 1 FROM rater_feedback    WHERE article_id = articles.id)
        """), {"ids": ids})
        return getattr(result, "rowcount", 0) or 0

    async with async_session() as db:
        # Candidates: un-analyzed, unlinked Telegram posts
        tg_rows = (await db.execute(
            select(TelegramPost.id, TelegramPost.text, TelegramPost.urls)
            .where(
                TelegramPost.story_id.is_(None),
                TelegramPost.sentiment_score.is_(None),
            )
        )).all()
        stats["tg_checked"] = len(tg_rows)
        tg_to_delete = [row.id for row in tg_rows if is_noise(row.text, row.urls or [])]
        if tg_to_delete:
            await db.execute(delete(TelegramPost).where(TelegramPost.id.in_(tg_to_delete)))
            stats["tg_deleted"] = len(tg_to_delete)

        # Candidates: un-embedded Telegram-originated articles. We
        # identify these by url prefix — convert_telegram_posts_to_articles
        # stamps them with `https://t.me/{channel}/{msg}`.
        art_rows = (await db.execute(
            _text("""
                SELECT id, title_fa, title_original, content_text
                FROM articles
                WHERE embedding IS NULL
                  AND story_id IS NULL
                  AND url LIKE 'https://t.me/%'
            """)
        )).all()
        stats["articles_checked"] = len(art_rows)
        art_to_delete = []
        for row in art_rows:
            # Combine whatever text we have; any of these can be the meat
            body = " ".join(
                p for p in (row.title_fa, row.title_original, row.content_text) if p
            )
            if is_noise(body, []):
                art_to_delete.append(row.id)
        deleted_n = await _delete_articles_safe(db, art_to_delete)
        stats["articles_deleted"] = deleted_n
        stats["articles_skipped_fk"] = len(art_to_delete) - deleted_n

        # Second pass — RSS-origin orphans with content_text < 200 chars.
        # These are usually feed stubs (nav fragments, "click to read",
        # empty bodies). Running after NLP has had a chance (ingested
        # >1h ago) so we don't prune articles still mid-extraction.
        # Restrict to story_id IS NULL so we never touch something that
        # made it into a cluster — there's a reason it landed there.
        SHORT_THRESHOLD = 200
        rss_short_rows = (await db.execute(
            _text("""
                SELECT id
                FROM articles
                WHERE story_id IS NULL
                  AND url NOT LIKE 'https://t.me/%'
                  AND ingested_at < NOW() - INTERVAL '1 hour'
                  AND (content_text IS NULL OR LENGTH(content_text) < :th)
            """), {"th": SHORT_THRESHOLD}
        )).all()
        stats["rss_short_checked"] = len(rss_short_rows)
        if rss_short_rows:
            ids = [row.id for row in rss_short_rows]
            deleted_n = await _delete_articles_safe(db, ids)
            stats["rss_short_deleted"] = deleted_n
            stats["rss_short_skipped_fk"] = len(ids) - deleted_n

        await db.commit()

    logger.info(
        f"Prune noise: tg {stats['tg_deleted']}/{stats['tg_checked']}, "
        f"tg-articles {stats['articles_deleted']}/{stats['articles_checked']}, "
        f"rss-short {stats.get('rss_short_deleted', 0)}/{stats.get('rss_short_checked', 0)}"
    )
    return stats


async def step_classify_content_type():
    """Label every newly-ingested article as news / opinion / discussion /
    aggregation / other before it reaches NLP. Only labels in each
    source's allowed-list (default ``["news"]``) get processed
    downstream — the rest of the row is preserved for audit.
    """
    from app.database import async_session
    from app.services.content_type import classify_unclassified_articles

    async with async_session() as db:
        stats = await classify_unclassified_articles(db, batch_size=400)

    logger.info(f"Content-type classifier: {stats}")
    return stats


async def step_process():
    """Step 2: NLP processing — translate, embed, extract keywords."""
    from app.database import async_session
    from app.services.nlp_pipeline import process_unprocessed_articles
    from sqlalchemy import text as _text

    total_processed = 0
    async with async_session() as db:
        while True:
            stats = await process_unprocessed_articles(db)
            batch = stats.get("processed", 0)
            total_processed += batch
            if batch < 50:
                break
            logger.info(f"  Processed batch: {batch}")

        # Coverage probe — catches silent embedding failures. A zero-filled
        # vector passes `is not None` but breaks every cosine downstream,
        # so we sample the last 24h and log a warning above the threshold.
        row = (await db.execute(_text(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (
                     WHERE embedding IS NOT NULL
                       AND NOT EXISTS (
                         SELECT 1 FROM jsonb_array_elements_text(embedding) v
                         WHERE v::float <> 0
                       )
                   ) AS all_zero
            FROM articles
            WHERE ingested_at >= NOW() - interval '24 hours'
            """
        ))).one()
        total = row.total or 0
        zeros = row.all_zero or 0
        pct = 100 * zeros / max(1, total)
        if total:
            if pct >= 10:
                logger.warning(
                    f"Embedding health: {zeros}/{total} articles ingested in last 24h "
                    f"have all-zero embeddings ({pct:.1f}%) — OpenAI embeddings may be degraded"
                )
            else:
                logger.info(
                    f"Embedding health: {zeros}/{total} zero-vectors in last 24h ({pct:.1f}%)"
                )

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
                from app.services.llm_usage import log_llm_usage
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="translation.backfill_title",
                    usage=resp.usage,
                    meta={"batch_size": len(batch)},
                )
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

    Cost optimization: only score articles in VISIBLE stories (article_count >= 5).
    Also limits to one article per source per story (we don't need 5 Fars articles
    scored when 1 tells us their framing).

    Runs multiple batches per maintenance cycle so coverage catches up over time.
    """
    from app.config import settings
    from app.database import async_session
    from app.services.bias_scoring import score_unscored_articles

    if not (settings.openai_api_key or settings.anthropic_api_key):
        logger.warning("No LLM API key set — skipping bias scoring")
        return {"skipped": "no_llm_key"}

    MAX_PER_RUN = 100  # reduced from 150 — priority scoring saves cost
    BATCH = 30
    total = {"scored": 0, "failed": 0, "skipped": 0, "skipped_visible_only": 0}
    from app.services import maintenance_state as _ms
    async with async_session() as db:
        for batch_idx in range(MAX_PER_RUN // BATCH):
            _ms.update_step_progress(
                total["scored"], MAX_PER_RUN, label=f"batch {batch_idx + 1}"
            )
            stats = await score_unscored_articles(
                db, batch_size=BATCH, visible_stories_only=True,
            )
            total["scored"] += stats.get("scored", 0)
            total["failed"] += stats.get("failed", 0)
            total["skipped"] += stats.get("skipped", 0)
            if stats.get("scored", 0) + stats.get("failed", 0) == 0:
                break
    logger.info(f"Bias scoring: {total}")
    return total


async def step_recount_stories():
    """Recompute article_count + source_count from the actual attached
    articles. Fixes drift caused by step_flag_unrelated_articles /
    step_deduplicate_articles / manual detachments, which remove rows
    from articles.story_id but never decremented the cached counters
    on stories.{article_count, source_count}.

    One UPDATE … FROM (GROUP BY) per table → fast even at 400+ stories.
    Idempotent. Safe to run in every pipeline.
    """
    from sqlalchemy import text as _text

    from app.database import async_session

    async with async_session() as db:
        # Recount article_count. Stories with zero attached articles
        # keep their cached value intact (those are usually pending
        # cleanup and would zero out incorrectly).
        r1 = await db.execute(_text("""
            UPDATE stories s
               SET article_count = sub.c
              FROM (
                SELECT story_id, COUNT(*)::int AS c
                  FROM articles
                 WHERE story_id IS NOT NULL
                 GROUP BY story_id
              ) sub
             WHERE s.id = sub.story_id
               AND s.article_count <> sub.c
        """))
        r2 = await db.execute(_text("""
            UPDATE stories s
               SET source_count = sub.c
              FROM (
                SELECT story_id, COUNT(DISTINCT source_id)::int AS c
                  FROM articles
                 WHERE story_id IS NOT NULL
                 GROUP BY story_id
              ) sub
             WHERE s.id = sub.story_id
               AND s.source_count <> sub.c
        """))
        await db.commit()

    stats = {"articles_fixed": r1.rowcount or 0, "sources_fixed": r2.rowcount or 0}
    logger.info(f"Recount stories: {stats}")
    return stats


async def step_cluster():
    """Step 3: Cluster articles into stories.

    Passes a deadline 60s before the harness timeout so the inner LLM
    batch loop can stop dispatching cleanly instead of relying on
    `asyncio.wait_for` to cancel a stuck OpenAI request — the latter
    overshot to 39m on the 2026-04-27 run because the underlying
    coroutine was blocking and didn't honor cancellation.
    """
    import time as _time
    from app.database import async_session
    from app.services.clustering import cluster_articles

    timeout = STEP_TIMEOUTS_SEC.get("cluster", DEFAULT_STEP_TIMEOUT_SEC)
    deadline_ts = _time.time() + max(60, timeout - 60)
    async with async_session() as db:
        stats = await cluster_articles(db, deadline_ts=deadline_ts)
    logger.info(f"Clustering: {stats}")
    return stats


async def step_recluster_orphans():
    """Second-chance clustering for articles stranded by the main pass.

    Runs after step_cluster. Targets articles whose story_id is still
    NULL more than 6 hours after ingestion — late arrivals whose
    "sibling" articles existed when the first pass ran but hadn't
    formed a cluster yet, or articles that narrowly missed the default
    0.45 cosine threshold.

    Uses centroid cosine against existing non-locked stories with a
    looser threshold (0.40). Pure math, no LLM — cheap. Attaches the
    orphan if it finds any story whose centroid is close enough.

    Intentionally conservative: only matches against stories with
    article_count >= 2 (already multi-source, so a match is meaningful)
    and skips stories with a Niloofar is_edited flag so human-curated
    arcs don't pick up misfit articles.
    """
    from sqlalchemy import select, update
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.nlp.embeddings import cosine_similarity as _cs

    RETRY_THRESHOLD = 0.40
    MIN_ORPHAN_AGE_HOURS = 6
    MAX_PER_RUN = 500

    stats = {"checked": 0, "attached": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MIN_ORPHAN_AGE_HOURS)

    async with async_session() as db:
        # Candidates: orphan articles with embeddings, old enough
        orphans = (await db.execute(
            select(Article.id, Article.embedding).where(
                Article.story_id.is_(None),
                Article.embedding.isnot(None),
                Article.ingested_at < cutoff,
            ).limit(MAX_PER_RUN)
        )).all()

        if not orphans:
            return stats

        # Load all eligible stories once (cheaper than per-article query)
        stories = (await db.execute(
            select(Story.id, Story.centroid_embedding).where(
                Story.article_count >= 2,
                Story.centroid_embedding.isnot(None),
                Story.is_edited.is_(False),
            )
        )).all()

        if not stories:
            return stats

        stats["checked"] = len(orphans)
        attached_ids: dict[str, object] = {}  # article_id -> story_id

        for art_id, emb in orphans:
            best_sim = 0.0
            best_story = None
            for sid, cent in stories:
                try:
                    sim = _cs(emb, cent)
                except Exception:
                    continue
                if sim > best_sim:
                    best_sim = sim
                    best_story = sid
            if best_story and best_sim >= RETRY_THRESHOLD:
                attached_ids[art_id] = best_story

        for art_id, sid in attached_ids.items():
            await db.execute(
                update(Article).where(Article.id == art_id).values(story_id=sid)
            )
        stats["attached"] = len(attached_ids)
        await db.commit()

    if stats["attached"]:
        logger.info(
            f"Recluster orphans: {stats['attached']}/{stats['checked']} "
            f"attached at ≥{RETRY_THRESHOLD} cosine"
        )
    return stats


async def step_recompute_centroids():
    """Step 3b: Recompute story centroid embeddings.

    After clustering and embedding, each story needs an up-to-date centroid
    (mean of its articles' embeddings). This is used by the embedding
    pre-filter in _match_to_existing_stories to skip irrelevant story/article
    pairs before calling the LLM.

    Only updates stories whose centroid is NULL (new or invalidated).
    """
    from sqlalchemy import select

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.clustering import _compute_centroid

    stats = {"updated": 0, "skipped": 0}

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .where(
                Story.article_count >= 2,
                Story.centroid_embedding.is_(None),
            )
        )
        stories = list(result.scalars().all())

        for story in stories:
            emb_result = await db.execute(
                select(Article.embedding)
                .where(Article.story_id == story.id, Article.embedding.isnot(None))
            )
            embeddings = [row[0] for row in emb_result.all() if row[0]]
            centroid = _compute_centroid(embeddings)
            if centroid:
                story.centroid_embedding = centroid
                stats["updated"] += 1
            else:
                stats["skipped"] += 1

        await db.commit()

    if stats["updated"] > 0:
        logger.info(f"Centroid recompute: {stats['updated']} stories updated")
    return stats


async def step_merge_similar():
    """Step 3c: Merge visible stories with high title overlap.

    Finds story pairs with >50% title word overlap, asks LLM to confirm,
    then merges confirmed pairs. Runs after clustering + centroids so
    newly created stories are included. Runs before summarize so merged
    stories get a fresh summary with the correct title.
    """
    from app.database import async_session
    from app.services.clustering import merge_similar_visible_stories

    async with async_session() as db:
        merged = await merge_similar_visible_stories(db)
    return {"merged": merged}


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
        # دورنما tier — broader top-N for prose synthesis on top of the
        # structured analysis. Independent of premium_story_top_n.
        doornama_result = await db.execute(
            select(Story.id)
            .where(Story.article_count >= 5)
            .order_by(Story.priority.desc(), Story.trending_score.desc())
            .limit(settings.doornama_top_n)
        )
        doornama_top_ids = {row[0] for row in doornama_result.all()}

        # 2. Find stories that need a summary. Two flavors:
        #    (a) summary_fa is NULL — never analyzed
        #    (b) article set changed since last analysis (articles joined
        #        or left the cluster; detected via sorted-article-id hash
        #        stored inside the summary_en JSONB blob). That one
        #        catches clusters whose composition drifted since the
        #        last LLM run, so stale bias_explanation_fa doesn't keep
        #        citing outlets no longer in the cluster.
        #    is_edited stories are ALWAYS skipped so Niloofar's
        #    hand-edits aren't clobbered.
        MAX_STORIES_PER_RUN = 15  # quality over quantity — deep analysis on top 15 only
        retry_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        # #6 — is_edited stories are NO LONGER skipped if they have a
        # summary_anchor. Anchored stories refresh on the normal
        # cadence, but the LLM is constrained to preserve the
        # anchor's tone/vocabulary. Stories with is_edited=True AND
        # no anchor still skip (legacy behavior — protects manual
        # work that hasn't been migrated).
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(
                Story.article_count >= 5,
                (Story.llm_failed_at.is_(None)) | (Story.llm_failed_at < retry_cutoff),
                # Skip ONLY when is_edited and no anchor — preserves
                # untouched manual edits, lets anchored ones refresh.
                (Story.is_edited.is_(False)) | (Story.summary_anchor.isnot(None)),
            )
            .order_by(Story.article_count.desc())
        )
        scan_candidates = list(result.scalars().all())

        import hashlib as _hashlib
        def _articles_hash(story_obj: Story) -> str:
            ids = sorted(str(a.id) for a in (story_obj.articles or []))
            return _hashlib.md5(",".join(ids).encode()).hexdigest()[:12]

        # Maturity window — once a story has been stable for this long
        # past its last_updated_at, we freeze the analysis (lock it and
        # skip re-runs). Prevents per-story neutrality scores drifting
        # across maintenance runs long after the story stopped evolving.
        ANALYSIS_LOCK_HOURS = 48

        # #7 — layered re-eval triggers. Replace the binary
        # "articles_hash changed?" check with three signals:
        #   * volume: ≥VOLUME_TRIGGER new articles since last analysis
        #   * drift: cosine similarity of new-article centroid vs
        #     stored centroid < DRIFT_THRESHOLD → flag as a possible
        #     story split and SKIP refresh (let HITL handle it)
        #   * hash change with neither volume nor drift → still refresh
        #     (small drips of relevant articles are fine to integrate)
        # Maturity lock stays as the cost-saving safety net for now.
        VOLUME_TRIGGER = 5
        DRIFT_THRESHOLD = 0.75

        from app.nlp.embeddings import cosine_similarity as _cs_eval

        all_candidates: list[Story] = []
        newly_locked = 0
        split_candidates = 0
        for s in scan_candidates:
            if s.summary_fa is None:
                all_candidates.append(s)
                continue
            # Check blob for the last-run article hash. If missing or
            # different → re-analyze. Also read the lock timestamp.
            try:
                b = _json.loads(s.summary_en) if s.summary_en else {}
            except Exception:
                b = {}
            # Already locked → never re-analyze.
            if isinstance(b, dict) and b.get("analysis_locked_at"):
                continue
            last_hash = b.get("articles_hash") if isinstance(b, dict) else None
            cur_hash = _articles_hash(s)
            hash_changed = (last_hash != cur_hash)

            # New articles since last analysis — diff the article id
            # set against the previous hash's source set. We don't
            # have the old set, so use article_count as a proxy:
            # `new_articles = current_count - count_at_last_hash`.
            # Stored alongside the hash on each successful run.
            count_at_last = b.get("articles_count_at_hash") if isinstance(b, dict) else None
            new_articles = (s.article_count or 0) - (count_at_last or 0) if count_at_last is not None else None

            # Drift check — only when we have both centroid and recent
            # article embeddings. Compares the centroid against the
            # mean of articles ingested in the last 7 days. If they
            # diverge significantly, the cluster is drifting and
            # might be a different story now.
            drift_flag = False
            if hash_changed and s.centroid_embedding and new_articles and new_articles >= 3:
                recent = [a for a in (s.articles or []) if a.embedding and a.published_at and (datetime.now(timezone.utc) - (a.published_at if a.published_at.tzinfo else a.published_at.replace(tzinfo=timezone.utc))).days <= 7]
                if len(recent) >= 3:
                    # Mean of recent embeddings
                    dim = len(recent[0].embedding or [])
                    if dim > 0:
                        mean_recent = [sum(r.embedding[i] for r in recent) / len(recent) for i in range(dim)]
                        sim = _cs_eval(s.centroid_embedding, mean_recent)
                        if sim < DRIFT_THRESHOLD:
                            drift_flag = True
                            split_candidates += 1
                            # Stash a HITL hint inside the blob; the dashboard
                            # /dashboard/edit-stories surfaces these.
                            b["split_candidate"] = {
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                                "drift_cosine": round(float(sim), 3),
                                "new_articles_7d": len(recent),
                            }
                            s.summary_en = _json.dumps(b, ensure_ascii=False)
                            # Emit a story_event so /dashboard/learning shows it.
                            from app.services.events import log_event as _log_split
                            await _log_split(
                                db,
                                event_type="story_split_candidate",
                                actor="maintenance",
                                story_id=s.id,
                                signals={
                                    "drift_cosine": round(float(sim), 3),
                                    "new_articles_7d": len(recent),
                                },
                            )
                            # Don't refresh — the cluster might be wrong.
                            continue

            # Volume gate — refresh on EITHER large new-article batch OR
            # hash change. Small drips don't trigger refresh by themselves.
            volume_trigger = (new_articles is not None and new_articles >= VOLUME_TRIGGER)
            needs_rerun = hash_changed and (volume_trigger or count_at_last is None)

            # Maturity check — if story is older than the lock window AND
            # has a real analysis, stamp the lock and skip re-running.
            lu = s.last_updated_at
            if lu is not None:
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - lu).total_seconds() / 3600.0
                if age_h > ANALYSIS_LOCK_HOURS and isinstance(b, dict) and b.get("bias_explanation_fa"):
                    b["analysis_locked_at"] = datetime.now(timezone.utc).isoformat()
                    s.summary_en = _json.dumps(b, ensure_ascii=False)
                    newly_locked += 1
                    continue
            if needs_rerun:
                all_candidates.append(s)

        if newly_locked:
            logger.info(f"Summarize: locked {newly_locked} mature stories (>{ANALYSIS_LOCK_HOURS}h since last update)")
        if split_candidates:
            logger.info(f"Summarize: flagged {split_candidates} story(ies) as split candidates (centroid drift)")
        if newly_locked or split_candidates:
            await db.commit()

        # 3. Rank by analysis priority (bias-richness, not just article count)
        def _analysis_priority(s: Story) -> float:
            diversity = s.coverage_diversity_score or 0
            has_both = 1.0 if (s.covered_by_state and s.covered_by_diaspora) else 0.3
            source_factor = min((s.source_count or 0) / 6.0, 1.0)
            recency = min((s.trending_score or 0) / 20.0, 1.0)
            return diversity * 0.3 + has_both * 0.3 + source_factor * 0.2 + recency * 0.2

        all_candidates.sort(key=_analysis_priority, reverse=True)
        stories = all_candidates[:MAX_STORIES_PER_RUN]

        if not stories:
            logger.info("Summarize: all visible stories have summaries")
            return {"generated": 0, "premium": 0, "baseline": 0, "failed": 0, "skipped_low_priority": 0}

        skipped_low = len(all_candidates) - len(stories)

        logger.info(
            f"Generating summaries for {len(stories)} stories "
            f"(top {len(top_ids)} trending → {settings.story_analysis_premium_model}, "
            f"rest → {settings.story_analysis_model})..."
        )
        success = 0
        failed = 0
        premium_used = 0
        baseline_used = 0
        from app.services import maintenance_state as _ms
        _stories_total = len(stories)
        for _idx, story in enumerate(stories):
            _ms.update_step_progress(_idx, _stories_total, label="story analysis")
            # Smart article selection: pick diverse articles (one per source,
            # balanced across alignments) instead of just most recent.
            art_result = await db.execute(
                select(Article)
                .options(selectinload(Article.source))
                .where(Article.story_id == story.id)
                .order_by(Article.published_at.desc().nullslast())
                .limit(30)  # candidate pool
            )
            candidates = list(art_result.scalars().all())

            # Select one per source, prefer longest content
            by_source: dict = {}
            for a in candidates:
                sid = a.source_id
                if sid not in by_source or len(a.content_text or "") > len(by_source[sid].content_text or ""):
                    by_source[sid] = a

            # Balance across alignments (ensure both sides represented)
            by_align: dict = {}
            for a in by_source.values():
                align = a.source.state_alignment if a.source else "unknown"
                by_align.setdefault(align, []).append(a)

            top_articles = []
            slots_per_align = max(2, MAX_ARTICLES_PER_STORY // max(len(by_align), 1))
            for align_articles in by_align.values():
                top_articles.extend(align_articles[:slots_per_align])
            top_articles = top_articles[:MAX_ARTICLES_PER_STORY]

            if not top_articles:
                top_articles = candidates[:MAX_ARTICLES_PER_STORY]

            # Tier selection — decide BEFORE building articles_info so
            # we can send more content to premium-tier stories
            is_premium = story.id in top_ids
            # Premium: 6000 chars (~1500 tokens) per article — deep analysis
            # Baseline: 1500 chars (~375 tokens) — just enough for a summary
            content_cap = 6000 if is_premium else 1500

            from app.services.narrative_groups import narrative_group as _ng
            articles_info = [
                {
                    "id": str(a.id),
                    "source_slug": a.source.slug if a.source else None,
                    "title": a.title_original or a.title_fa or a.title_en or "",
                    "content": (a.content_text or a.summary or "")[:content_cap],
                    "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                    "state_alignment": a.source.state_alignment if a.source else "",
                    "production_location": a.source.production_location if a.source else None,
                    "factional_alignment": a.source.factional_alignment if a.source else None,
                    "narrative_group": _ng(a.source) if a.source else "moderate_diaspora",
                    "published_at": a.published_at.isoformat() if a.published_at else "",
                }
                for a in top_articles
            ]
            if is_premium:
                chosen_model = settings.story_analysis_premium_model
                tier_label = "premium"
            else:
                chosen_model = settings.story_analysis_model
                tier_label = "baseline"
            try:
                await _keepalive(db)
                is_premium = (tier_label == "premium")

                # Cross-story memory: find related stories with existing summaries
                related = []
                if story.centroid_embedding:
                    from app.nlp.embeddings import cosine_similarity as _cs
                    rel_result = await db.execute(
                        select(Story.id, Story.title_fa, Story.summary_fa, Story.centroid_embedding)
                        .where(
                            Story.id != story.id,
                            Story.summary_fa.isnot(None),
                            Story.centroid_embedding.isnot(None),
                            Story.article_count >= 5,
                        )
                        .order_by(Story.trending_score.desc())
                        .limit(20)
                    )
                    for rid, rtitle, rsummary, rcentroid in rel_result.all():
                        if rcentroid:
                            sim = _cs(story.centroid_embedding, rcentroid)
                            if sim > 0.5:
                                related.append({"title": rtitle, "summary": rsummary})
                                if len(related) >= 3:
                                    break

                # Source track records: narrative-subgroup heuristic
                from app.services.narrative_groups import narrative_group as _ng_tr
                source_records = {}
                source_slugs = {a.source.slug for a in top_articles if a.source}
                _TRACK = {
                    "principlist": "اصول‌گرا — تمایل به بزرگ‌نمایی دستاوردها و کوچک‌نمایی تلفات",
                    "reformist": "اصلاح‌طلب — نسبتاً محتاط داخل ایران، گاهی انتقادی",
                    "moderate_diaspora": "میانه‌رو — پوشش گزارش‌گونه بین‌المللی",
                    "radical_diaspora": "رادیکال — تمایل به تأکید بر سرکوب و نقض حقوق بشر",
                }
                for slug in list(source_slugs)[:6]:
                    src = next((a.source for a in top_articles if a.source and a.source.slug == slug), None)
                    if src:
                        source_records[slug] = _TRACK.get(_ng_tr(src), "")

                # Save old summary for delta detection before overwriting
                _old_summary = story.summary_fa

                analysis = await generate_story_analysis(
                    story, articles_info,
                    model=chosen_model,
                    include_analyst_factors=is_premium,
                    related_stories=related if related else None,
                    source_track_records=source_records if source_records else None,
                    old_summary=_old_summary,
                    summary_anchor=story.summary_anchor,
                )
                story.summary_fa = analysis.get("summary_fa")
                # Update title if LLM returned a better one
                if analysis.get("title_fa") and analysis["title_fa"].strip():
                    story.title_fa = analysis["title_fa"].strip()
                if analysis.get("title_en") and analysis["title_en"].strip():
                    story.title_en = analysis["title_en"].strip()
                # Preserve Claude-scored neutrality across LLM re-runs —
                # the LLM no longer produces these fields, they come from
                # scripts/neutrality_audit.py. Read old extras first and
                # carry them forward.
                try:
                    old_extras = _json.loads(story.summary_en) if story.summary_en else {}
                except Exception:
                    old_extras = {}
                extras = {
                    "state_summary_fa": analysis.get("state_summary_fa"),
                    "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                    "independent_summary_fa": analysis.get("independent_summary_fa"),
                    "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                    "scores": analysis.get("scores"),
                    "llm_model_used": chosen_model,
                }
                # Carry Claude-scored neutrality forward
                for k in ("source_neutrality", "article_neutrality", "neutrality_source", "neutrality_scored_at"):
                    if isinstance(old_extras, dict) and old_extras.get(k) is not None:
                        extras[k] = old_extras[k]
                # Deterministic evidence (loaded-word hits, quote count,
                # word count) per article. Cheap, no LLM — fresh every run.
                if analysis.get("article_evidence"):
                    extras["article_evidence"] = analysis["article_evidence"]
                # Store dispute score for homepage "most disputed" section
                if analysis.get("dispute_score") is not None:
                    extras["dispute_score"] = analysis["dispute_score"]
                # Store loaded words for homepage "words of the week" section
                if analysis.get("loaded_words"):
                    extras["loaded_words"] = analysis["loaded_words"]
                # Store narrative arc for story evolution tracking
                if analysis.get("narrative_arc"):
                    extras["narrative_arc"] = analysis["narrative_arc"]
                # Store delta — what's new since last analysis
                if analysis.get("delta"):
                    extras["delta"] = analysis["delta"]
                # Store analyst factors for premium stories
                if is_premium and analysis.get("analyst"):
                    extras["analyst"] = analysis["analyst"]
                # Stamp the article-set hash so the next pipeline run can
                # detect composition drift and re-analyze — see the
                # articles_hash check above in step_summarize.
                extras["articles_hash"] = _articles_hash(story)
                # #7 — also stamp the article count at this hash so the
                # next run can compute "new articles since last analysis"
                # for the volume trigger. Replaces the old simple "any
                # hash change → rerun" rule.
                extras["articles_count_at_hash"] = story.article_count or 0

                # دورنما — narrative-synthesis prose for the top N
                # trending stories. Skip-if-unchanged via briefing_hash
                # so unchanged top stories don't re-pay the LLM cost
                # on every pass.
                if story.id in doornama_top_ids:
                    from app.services.doornama import (
                        compute_briefing_hash,
                        generate_doornama_briefing,
                    )

                    prior = old_extras if isinstance(old_extras, dict) else {}
                    new_hash = compute_briefing_hash(
                        state_summary_fa=extras.get("state_summary_fa"),
                        diaspora_summary_fa=extras.get("diaspora_summary_fa"),
                        independent_summary_fa=extras.get("independent_summary_fa"),
                        bias_explanation_fa=extras.get("bias_explanation_fa"),
                        silence_analysis=extras.get("silence_analysis"),
                        narrative_arc=extras.get("narrative_arc"),
                    )
                    if new_hash == prior.get("briefing_hash") and prior.get("briefing_fa"):
                        # Inputs unchanged — carry the prior briefing forward.
                        extras["briefing_fa"] = prior["briefing_fa"]
                        extras["briefing_hash"] = prior["briefing_hash"]
                    else:
                        anchor_briefing = None
                        if isinstance(story.summary_anchor, dict):
                            anchor_briefing = story.summary_anchor.get("briefing_fa")
                        await _keepalive(db)
                        result = await generate_doornama_briefing(
                            story_id=str(story.id),
                            title_fa=story.title_fa,
                            state_summary_fa=extras.get("state_summary_fa"),
                            diaspora_summary_fa=extras.get("diaspora_summary_fa"),
                            independent_summary_fa=extras.get("independent_summary_fa"),
                            bias_explanation_fa=extras.get("bias_explanation_fa"),
                            silence_analysis=extras.get("silence_analysis"),
                            narrative_arc=extras.get("narrative_arc"),
                            summary_anchor_briefing_fa=anchor_briefing,
                        )
                        if result:
                            extras["briefing_fa"] = result["briefing_fa"]
                            extras["briefing_hash"] = result["briefing_hash"]
                        elif prior.get("briefing_fa"):
                            # On failure, leave any prior briefing in
                            # place — better stale than empty.
                            extras["briefing_fa"] = prior["briefing_fa"]
                            extras["briefing_hash"] = prior.get("briefing_hash")

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
    from sqlalchemy import select, update as _upd
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

    # --- Pass 1: HEAD-check up to 300 article images ---
    # Read-only session for the SELECT, then close it so we don't hold a
    # connection across ~300 HTTP HEADs (which is what let Neon kill the
    # connection mid-loop in the 2026-04-27 incident — InterfaceError
    # "connection is closed"). Updates flushed in fresh-session chunks below.
    check_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with async_session() as db:
        result = await db.execute(
            select(Article.id, Article.image_url)
            .where(
                Article.image_url.isnot(None),
                (Article.image_checked_at.is_(None)) | (Article.image_checked_at < check_cutoff),
            )
            .limit(300)
        )
        rows = result.all()
    stats["skipped_recent"] = 0  # will be set when we know how many we skipped
    now_ts = datetime.now(timezone.utc)

    pending: list[tuple] = []  # (article_id, new_image_url_or_None)
    from app.services import maintenance_state as _ms
    total_n = len(rows)
    async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
        for idx, (art_id, art_url) in enumerate(rows):
            stats["checked"] += 1
            if idx % 10 == 0:
                _ms.update_step_progress(idx, total_n, label="HEAD-checking images")
            if art_url and art_url.startswith("http://localhost"):
                pending.append((art_id, None))
                stats["nulled"] += 1
                continue
            try:
                r = await client.head(art_url)
                if r.status_code != 200:
                    pending.append((art_id, None))
                    stats["nulled"] += 1
                else:
                    # URL is healthy — only update image_checked_at, not URL.
                    pending.append((art_id, art_url))  # leave URL unchanged
            except Exception:
                pending.append((art_id, None))
                stats["nulled"] += 1
    _ms.update_step_progress(total_n, total_n, label="HEAD-check done")

    # Flush updates in chunks of 100 with a fresh session per chunk. Each
    # chunk's connection is short-lived enough to escape the idle reaper.
    BATCH = 100
    for i in range(0, len(pending), BATCH):
        chunk = pending[i:i + BATCH]
        async with async_session() as db_chunk:
            for art_id, new_url in chunk:
                await db_chunk.execute(
                    _upd(Article)
                    .where(Article.id == art_id)
                    .values(image_url=new_url, image_checked_at=now_ts)
                )
            await db_chunk.commit()

    # --- Pass 2: For visible stories WITHOUT any working image,
    # try to fetch an og:image from one of their article URLs.
    # Note: Story has no image_url column — image selection happens
    # at response time in _story_brief_with_extras() using a
    # title-overlap heuristic across story.articles. We don't set
    # story.image_url here because the attribute doesn't exist on
    # the Story model.
    # Pass 2 owns its own httpx client; the Pass 1 client closed before
    # the chunked write phase. Story-walk uses ORM mutations + a single
    # commit at the end (200-row cap means each session is short-lived,
    # so the same Neon-reaper risk doesn't apply here).
    async with async_session() as db, httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
        result = await db.execute(
            select(Story).options(selectinload(Story.articles))
            .where(Story.article_count >= 5)
            .limit(200)  # cap to avoid loading all stories into memory
        )
        for story in result.scalars().all():
            # Any article with a live image_url is enough for the
            # response-time picker to work.
            has_image = any(a.image_url for a in story.articles)
            if has_image:
                continue
            # Try 1: og:image from non-Telegram article URLs
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
            # Try 2: Telegram embed image (for Telegram-only stories)
            if not fetched:
                for a in story.articles:
                    if a.url and "t.me/" in a.url:
                        try:
                            embed_url = a.url.rstrip("/") + "?embed=1"
                            r = await client.get(embed_url)
                            if r.status_code == 200:
                                import re
                                # Look for background-image or og:image in embed HTML
                                match = re.search(r"background-image:\s*url\('([^']+)'\)", r.text)
                                if not match:
                                    match = re.search(r'<img[^>]+src="(https://cdn[^"]+)"', r.text)
                                if match:
                                    a.image_url = match.group(1)
                                    a.image_checked_at = now_ts
                                    stats["replaced"] += 1
                                    fetched = True
                                    break
                        except Exception:
                            continue
            if not fetched:
                stats["stories_without_image"] += 1

        await db.commit()

    if any(v > 0 for v in stats.values()):
        logger.info(f"Image fix: {stats}")
    return stats


async def step_story_quality():
    """Step 4c: Story quality — merge duplicates, regenerate stale summaries, score quality.

    Each LLM-driven summary regeneration runs in its own fresh DB session
    so the prior 50s+ of OpenAI calls (5 stories × ~10s each) doesn't
    leave the connection idle long enough for Neon's reaper to kill it
    mid-run. The 2026-04-27 incident hit this exact path with
    `InterfaceError: connection is closed` on UPDATE stories.
    """
    import json as _json
    from sqlalchemy import select, update as _upd
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.story_analysis import generate_story_analysis

    stats = {"summaries_regenerated": 0, "duplicates_flagged": 0, "stale_cleared": 0}

    # Phase 1 — mark stale stories that have grown ≥3 articles since the
    # last summary. ORM scan, single-session, single commit at the end.
    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(
                Story.article_count >= 5,
                Story.summary_fa.isnot(None),
                Story.is_edited.is_(False),
            )
        )
        for story in result.scalars().all():
            actual_count = len(story.articles)
            if actual_count >= story.article_count + 3:
                story.summary_fa = None
                story.summary_en = None
                story.article_count = actual_count
                stats["stale_cleared"] += 1
        await db.commit()

    # Phase 2 — pull the stories that still need a summary. Read into a
    # plain list, close the read session, then loop without holding it
    # across LLM calls.
    from app.config import settings
    if not settings.openai_api_key:
        if stats["stale_cleared"] > 0 or stats["summaries_regenerated"] > 0:
            logger.info(f"Story quality: {stats}")
        return stats

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 5, Story.summary_fa.is_(None))
            .order_by(Story.article_count.desc())
            .limit(5)  # Max 5 per run to control costs
        )
        targets = list(result.scalars().all())
        # Snapshot every field we need so we can detach from the session.
        from app.services.narrative_groups import narrative_group as _ng2
        snapshots = []
        for story in targets:
            snapshots.append({
                "id": story.id,
                "title_fa": story.title_fa,
                "summary_en_old": story.summary_en,
                "story_obj": story,  # needed by generate_story_analysis
                "articles_info": [
                    {
                        "id": str(a.id),
                        "source_slug": a.source.slug if a.source else None,
                        "title": a.title_original or a.title_fa or a.title_en or "",
                        "content": (a.content_text or a.summary or "")[:1500],
                        "source_name_fa": a.source.name_fa if a.source else "نامشخص",
                        "state_alignment": a.source.state_alignment if a.source else "",
                        "production_location": a.source.production_location if a.source else None,
                        "factional_alignment": a.source.factional_alignment if a.source else None,
                        "narrative_group": _ng2(a.source) if a.source else "moderate_diaspora",
                        "published_at": a.published_at.isoformat() if a.published_at else "",
                    }
                    for a in story.articles
                ],
            })
    # `db` released — no DB session held during the LLM phase below.

    for snap in snapshots:
        try:
            analysis = await generate_story_analysis(snap["story_obj"], snap["articles_info"])
            try:
                _old = _json.loads(snap["summary_en_old"]) if snap["summary_en_old"] else {}
            except Exception:
                _old = {}
            _new = {
                "state_summary_fa": analysis.get("state_summary_fa"),
                "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                "independent_summary_fa": analysis.get("independent_summary_fa"),
                "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                "scores": analysis.get("scores"),
                "article_evidence": analysis.get("article_evidence"),
                "dispute_score": analysis.get("dispute_score"),
                "loaded_words": analysis.get("loaded_words"),
            }
            for k in ("source_neutrality", "article_neutrality", "neutrality_source", "neutrality_scored_at"):
                if isinstance(_old, dict) and _old.get(k) is not None:
                    _new[k] = _old[k]
            new_summary_en = _json.dumps(_new, ensure_ascii=False)

            updates = {
                "summary_fa": analysis.get("summary_fa"),
                "summary_en": new_summary_en,
            }
            if analysis.get("title_fa"):
                updates["title_fa"] = analysis["title_fa"].strip()
            if analysis.get("title_en"):
                updates["title_en"] = analysis["title_en"].strip()

            # Fresh session per write — bounds the connection's idle wall-
            # clock to a single UPDATE, well under any reaper threshold.
            async with async_session() as db_w:
                await db_w.execute(
                    _upd(Story).where(Story.id == snap["id"]).values(**updates)
                )
                await db_w.commit()
            stats["summaries_regenerated"] += 1
            logger.info(f"  Regenerated summary: {(snap['title_fa'] or '')[:40]}")
        except Exception as e:
            logger.warning(f"  Failed: {(snap['title_fa'] or '')[:40]}: {e}")

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
    """Step 4e: Track OpenAI API costs from maintenance runs.

    Only useful in local dev where the `project-management/` sibling of
    `backend/` actually exists. On Railway `__file__` lives near the
    container root so the path resolves to `/project-management/…` which
    is unwritable — skip cleanly instead of failing the pipeline.
    """
    from pathlib import Path

    log_file = Path(__file__).parent.parent / "project-management" / "COST_LOG.md"
    if not log_file.parent.exists():
        return {"skipped": True, "reason": "project-management dir not present (production)"}

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
    """Apply «نامرتبط» feedback to actually move articles.

    Two consensus paths:

    Rater (trusted, token-authed): 1 trusted rater is enough — Doornegar
    is small and Parham hand-picks raters, so a single «نامرتبط» click
    acts on the next maintenance tick (≤24h grace from cron cadence).

    Anonymous (public «نامرتبط» button): 3 distinct submitter fingerprints
    on the same article via wrong_clustering. Fingerprint is sha256(IP +
    UA + lang) computed at submission time — not strong identity, just a
    deterrent to single-IP brigading.

    After orphaning, articles are run back through cosine matching to
    find a *better* home. The (article, story) pair the user explicitly
    rejected is excluded from the candidate set, so «نامرتبط» actually
    means "find a better cluster" instead of "remove from view".
    """
    from sqlalchemy import select, func, update, distinct
    from app.database import async_session
    from app.models.feedback import RaterFeedback
    from app.models.improvement import ImprovementFeedback
    from app.models.article import Article
    from app.models.story import Story
    from app.nlp.embeddings import cosine_similarity as _cs
    from app.services.events import log_event as _log_event

    stats = {
        "rater_orphaned": 0,
        "anon_orphaned": 0,
        "rehomed": 0,
        "still_orphan": 0,
    }
    rejections: set[tuple[str, str]] = set()
    orphan_ids: set[uuid.UUID] = set()
    # Track orphan→from-story mapping so we can log a follow-up rehome
    # event linking the two stories.
    orphan_from: dict[uuid.UUID, uuid.UUID] = {}

    async with async_session() as db:
        # ── Rater path: ≥1 trusted vote ─────────────────────────
        rater_groups = (await db.execute(
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
            .having(func.count(RaterFeedback.id) >= 1)
        )).all()

        for art_id, sid, votes in rater_groups:
            if not (art_id and sid):
                continue
            rejections.add((str(art_id), str(sid)))
            res = await db.execute(
                update(Article)
                .where(Article.id == art_id, Article.story_id == sid)
                .values(story_id=None)
            )
            if res.rowcount:
                stats["rater_orphaned"] += 1
                orphan_ids.add(art_id)
                orphan_from[art_id] = sid
                await _log_event(
                    db,
                    event_type="feedback_orphan_rater",
                    actor="rater_feedback",
                    story_id=sid,
                    article_id=art_id,
                    signals={"votes": int(votes)},
                )
                logger.info(
                    f"  Rater feedback: orphaned article {art_id} "
                    f"from story {sid} ({votes} vote{'s' if votes != 1 else ''})"
                )

        # ── Anonymous path: ≥3 distinct *identities* ────────────
        # An identity is the strongest available signal for each row:
        # COALESCE(submitter_cookie, submitter_fingerprint). Cookie is
        # the harder-to-spoof one (long-lived UUID per browser), but
        # older rows from before the cookie column existed only have
        # the IP+UA fingerprint, so we fall through. Counting distinct
        # COALESCEs catches the "private-mode reload" gaming pattern
        # the IP+UA-only check used to allow.
        identity_expr = func.coalesce(
            ImprovementFeedback.submitter_cookie,
            ImprovementFeedback.submitter_fingerprint,
        )
        anon_groups = (await db.execute(
            select(
                ImprovementFeedback.target_id,
                func.count(distinct(identity_expr)).label("voters"),
            )
            .where(
                ImprovementFeedback.target_type == "article",
                ImprovementFeedback.issue_type == "wrong_clustering",
                ImprovementFeedback.status == "open",
                identity_expr.isnot(None),
            )
            .group_by(ImprovementFeedback.target_id)
            .having(func.count(distinct(identity_expr)) >= 3)
        )).all()

        for art_id_str, voters in anon_groups:
            if not art_id_str:
                continue
            try:
                article_uuid = uuid.UUID(art_id_str)
            except ValueError:
                continue
            current_sid = (await db.execute(
                select(Article.story_id).where(Article.id == article_uuid)
            )).scalar_one_or_none()
            if not current_sid:
                continue
            rejections.add((str(article_uuid), str(current_sid)))
            res = await db.execute(
                update(Article)
                .where(Article.id == article_uuid, Article.story_id == current_sid)
                .values(story_id=None)
            )
            if res.rowcount:
                stats["anon_orphaned"] += 1
                orphan_ids.add(article_uuid)
                orphan_from[article_uuid] = current_sid
                # Persist the from-story for the negative-pair check and
                # mark submissions in_progress so we don't re-trigger on
                # the next tick before rehoming completes.
                await db.execute(
                    update(ImprovementFeedback)
                    .where(
                        ImprovementFeedback.target_id == art_id_str,
                        ImprovementFeedback.issue_type == "wrong_clustering",
                        ImprovementFeedback.status == "open",
                    )
                    .values(
                        status="in_progress",
                        orphaned_from_story_id=current_sid,
                        admin_notes=f"Auto-orphaned at {voters} fingerprints",
                        resolved_at=datetime.now(timezone.utc),
                    )
                )
                await _log_event(
                    db,
                    event_type="feedback_orphan_anon",
                    actor="improvement_feedback",
                    story_id=current_sid,
                    article_id=article_uuid,
                    signals={"voters": int(voters)},
                )
                logger.info(
                    f"  Anon feedback: orphaned article {article_uuid} "
                    f"from story {current_sid} ({voters} fingerprints)"
                )

        await db.commit()

        # ── Rehome: try to find a better cluster for the orphans ──
        if orphan_ids:
            orphan_articles = (await db.execute(
                select(Article.id, Article.embedding).where(
                    Article.id.in_(orphan_ids),
                    Article.embedding.isnot(None),
                )
            )).all()

            stories = (await db.execute(
                select(Story.id, Story.centroid_embedding).where(
                    Story.article_count >= 2,
                    Story.centroid_embedding.isnot(None),
                    Story.is_edited.is_(False),
                )
            )).all()

            RETRY_THRESHOLD = 0.40

            for art_id, emb in orphan_articles:
                best_sim = 0.0
                best_story = None
                for sid, cent in stories:
                    if (str(art_id), str(sid)) in rejections:
                        continue  # honor the user's explicit rejection
                    try:
                        sim = _cs(emb, cent)
                    except Exception:
                        continue
                    if sim > best_sim:
                        best_sim = sim
                        best_story = sid
                if best_story and best_sim >= RETRY_THRESHOLD:
                    await db.execute(
                        update(Article).where(Article.id == art_id).values(story_id=best_story)
                    )
                    stats["rehomed"] += 1
                    await _log_event(
                        db,
                        event_type="feedback_rehome",
                        actor="rater_feedback",
                        story_id=best_story,
                        article_id=art_id,
                        confidence=float(best_sim),
                        signals={
                            "from_story_id": str(orphan_from.get(art_id) or ""),
                            "cosine": round(best_sim, 3),
                        },
                    )
                    logger.info(
                        f"  Rehomed article {art_id} → story {best_story} "
                        f"(cosine {best_sim:.2f})"
                    )
                else:
                    stats["still_orphan"] += 1
            await db.commit()

    if any(stats.values()):
        logger.info(f"Rater feedback apply: {stats}")
    return stats


async def step_apply_summary_corrections():
    """Regenerate story summaries when raters submit corrections.

    Picks rater_feedback rows where:
      - feedback_type = summary_accuracy
      - summary_rating ≤ 2 (low score)
      - summary_correction is non-empty
      - applied_at IS NULL (not yet processed)

    Skips stories with is_edited=True (respect manual edits). Caps at
    20 stories per run for cost. Marks the feedback row applied_at on
    success so it doesn't replay.
    """
    from sqlalchemy import select, update

    from app.config import settings
    from app.database import async_session
    from app.models.feedback import RaterFeedback
    from app.models.story import Story

    stats = {"regenerated": 0, "skipped": 0, "failed": 0}

    async with async_session() as db:
        rows = (await db.execute(
            select(RaterFeedback, Story)
            .join(Story, Story.id == RaterFeedback.story_id)
            .where(
                RaterFeedback.feedback_type == "summary_accuracy",
                RaterFeedback.summary_rating <= 2,
                RaterFeedback.summary_correction.isnot(None),
                RaterFeedback.applied_at.is_(None),
                Story.is_edited.is_(False),
                Story.summary_fa.isnot(None),
            )
            .limit(20)
        )).all()

        if not rows:
            return stats

        import openai
        from app.services.llm_helper import build_openai_params
        from app.services.llm_usage import log_llm_usage
        from app.services.events import log_event as _log_event

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        prompt_template = """تو ویراستار ارشد دورنگر هستی.
خلاصه فعلی این خبر داریم. خواننده‌ای بازخورد داده که خلاصه دقیق نیست.
وظیفه: خلاصه را با در نظر گرفتن بازخورد، در ۲ تا ۴ جمله بازنویسی کن.

عنوان: {title_fa}

خلاصه فعلی:
{summary_current}

بازخورد خواننده:
{correction}

دستورالعمل:
- لحن تحلیلی، داده‌محور (نه ادبی)
- بدون قضاوت — فقط واقعیت‌ها
- بدون تکرار عنوان
- فقط متن خلاصه را برگردان"""

        for fb, story in rows:
            try:
                prompt = prompt_template.format(
                    title_fa=story.title_fa or "",
                    summary_current=(story.summary_fa or "")[:600],
                    correction=(fb.summary_correction or "")[:400],
                )
                params = build_openai_params(
                    model=settings.translation_model,
                    prompt=prompt,
                    max_tokens=512,
                    temperature=0.3,
                )
                response = await client.chat.completions.create(**params)
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="feedback.summary_regen",
                    usage=response.usage,
                    story_id=story.id,
                )
                new_summary = (response.choices[0].message.content or "").strip()
                if new_summary and len(new_summary) > 30:
                    await db.execute(
                        update(Story)
                        .where(Story.id == story.id)
                        .values(summary_fa=new_summary)
                    )
                    await db.execute(
                        update(RaterFeedback)
                        .where(RaterFeedback.id == fb.id)
                        .values(applied_at=datetime.now(timezone.utc))
                    )
                    await _log_event(
                        db,
                        event_type="feedback_summary_regen",
                        actor="rater_feedback",
                        story_id=story.id,
                        signals={
                            "rating": int(fb.summary_rating or 0),
                            "correction_chars": len(fb.summary_correction or ""),
                        },
                    )
                    stats["regenerated"] += 1
                    logger.info(f"  Regenerated summary for story {story.id} from rater correction")
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"Summary regen failed for story {story.id}: {e}")

        # ── R2 — anonymous summary corrections via improvement_feedback ──
        # SummaryRating now also writes to improvement_feedback for anon
        # users. We act on a story when ≥3 distinct identities (cookie
        # or IP fingerprint) flagged it with `bad_summary`. Each row
        # may carry a suggested correction in `suggested_value`; we
        # concatenate up to 5 of them as the prompt input.
        from sqlalchemy import distinct
        from app.models.improvement import ImprovementFeedback as _IF

        remaining_cap = max(0, 20 - stats["regenerated"])
        if remaining_cap > 0:
            identity_expr = func.coalesce(_IF.submitter_cookie, _IF.submitter_fingerprint)
            anon_groups = (await db.execute(
                select(
                    _IF.target_id,
                    func.count(distinct(identity_expr)).label("voters"),
                )
                .where(
                    _IF.target_type == "story_summary",
                    _IF.issue_type == "bad_summary",
                    _IF.status == "open",
                    identity_expr.isnot(None),
                )
                .group_by(_IF.target_id)
                .having(func.count(distinct(identity_expr)) >= 3)
                .limit(remaining_cap)
            )).all()

            for target_id, voters in anon_groups:
                if not target_id:
                    continue
                try:
                    story_uuid = uuid.UUID(target_id)
                except ValueError:
                    continue
                story = (await db.execute(
                    select(Story).where(Story.id == story_uuid)
                )).scalar_one_or_none()
                if not story or story.is_edited or not story.summary_fa:
                    continue
                # Pull up to 5 actual correction texts to feed the LLM.
                corr_rows = (await db.execute(
                    select(_IF.suggested_value, _IF.reason)
                    .where(
                        _IF.target_type == "story_summary",
                        _IF.target_id == target_id,
                        _IF.issue_type == "bad_summary",
                        _IF.status == "open",
                    )
                    .limit(5)
                )).all()
                corrections_lines: list[str] = []
                for sv, rs in corr_rows:
                    txt = (sv or rs or "").strip()
                    if txt and len(txt) >= 5:
                        corrections_lines.append(f"- {txt[:200]}")
                if not corrections_lines:
                    # Multiple low ratings but no actual text — count as
                    # signal but don't have anything to feed the LLM.
                    # Mark in_progress so we stop polling these rows.
                    await db.execute(
                        update(_IF)
                        .where(
                            _IF.target_type == "story_summary",
                            _IF.target_id == target_id,
                            _IF.issue_type == "bad_summary",
                            _IF.status == "open",
                        )
                        .values(status="wont_do", admin_notes="No correction text provided.", resolved_at=datetime.now(timezone.utc))
                    )
                    continue
                combined_correction = (
                    f"چند خواننده ({int(voters)} نفر) گفته‌اند خلاصه نادرست است. اصلاحات پیشنهادی:\n"
                    + "\n".join(corrections_lines)
                )
                try:
                    prompt = prompt_template.format(
                        title_fa=story.title_fa or "",
                        summary_current=(story.summary_fa or "")[:600],
                        correction=combined_correction[:1000],
                    )
                    params = build_openai_params(
                        model=settings.translation_model,
                        prompt=prompt,
                        max_tokens=512,
                        temperature=0.3,
                    )
                    response = await client.chat.completions.create(**params)
                    await log_llm_usage(
                        model=settings.translation_model,
                        purpose="feedback.summary_regen_anon",
                        usage=response.usage,
                        story_id=story.id,
                    )
                    new_summary = (response.choices[0].message.content or "").strip()
                    if new_summary and len(new_summary) > 30:
                        await db.execute(
                            update(Story)
                            .where(Story.id == story.id)
                            .values(summary_fa=new_summary)
                        )
                        await db.execute(
                            update(_IF)
                            .where(
                                _IF.target_type == "story_summary",
                                _IF.target_id == target_id,
                                _IF.issue_type == "bad_summary",
                                _IF.status == "open",
                            )
                            .values(status="done", resolved_at=datetime.now(timezone.utc))
                        )
                        await _log_event(
                            db,
                            event_type="feedback_summary_regen",
                            actor="anon_consensus",
                            story_id=story.id,
                            signals={"voters": int(voters), "corrections_used": len(corrections_lines)},
                        )
                        stats["regenerated"] += 1
                        logger.info(f"  Regenerated summary for story {story.id} from anon consensus ({voters} voters)")
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(f"Anon summary regen failed for story {story.id}: {e}")

        await db.commit()

    if stats["regenerated"]:
        logger.info(f"Summary corrections applied: {stats}")
    return stats


async def step_niloofar_feedback_audit():
    """Niloofar reviews open wrong_clustering items that haven't reached
    the 3-fingerprint anonymous threshold.

    Picks ImprovementFeedback rows older than 24h (so the auto-apply
    path got first chance), reads the article + story it's currently
    in, and asks Niloofar to judge:
      - "agree" → orphan article + mark in_progress
      - "disagree" → close as wont_do with explanation
      - "ambiguous" → leave open for Parham

    Capped at 20 per run.
    """
    from sqlalchemy import select, update

    from app.config import settings
    from app.database import async_session
    from app.models.improvement import ImprovementFeedback
    from app.models.article import Article
    from app.models.story import Story

    stats = {"agreed": 0, "disagreed": 0, "ambiguous": 0, "stale": 0, "failed": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with async_session() as db:
        rows = (await db.execute(
            select(ImprovementFeedback)
            .where(
                ImprovementFeedback.target_type == "article",
                ImprovementFeedback.issue_type == "wrong_clustering",
                ImprovementFeedback.status == "open",
                ImprovementFeedback.created_at < cutoff,
            )
            .limit(20)
        )).scalars().all()

        if not rows:
            return stats

        import openai
        from app.services.llm_helper import build_openai_params
        from app.services.llm_usage import log_llm_usage
        from app.services.events import log_event as _log_event

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        prompt_template = """تو نیلوفر هستی، سردبیر ارشد دورنگر.
یک خواننده گزارش داده که این مقاله در خوشهٔ اشتباه قرار گرفته است.

موضوع خوشه: {story_title}
خلاصهٔ خوشه: {story_summary}

عنوان مقاله: {article_title}
متن مقاله (چند سطر اول): {article_excerpt}

سؤال: آیا این مقاله به موضوع خوشه مربوط است؟
- agree — اگر مقاله نامرتبط است (خواننده حق دارد)
- disagree — اگر مقاله مرتبط است (خواننده اشتباه می‌کند)
- ambiguous — اگر معلوم نیست

پاسخ را در سطر اول فقط با یک کلمه (agree / disagree / ambiguous) بده،
و در سطر بعد یک جملهٔ کوتاه برای توضیح."""

        for fb in rows:
            if not fb.target_id:
                continue
            try:
                article_uuid = uuid.UUID(fb.target_id)
            except ValueError:
                stats["failed"] += 1
                continue

            article = (await db.execute(
                select(Article).where(Article.id == article_uuid)
            )).scalar_one_or_none()
            if not article or not article.story_id:
                # Already orphaned by another path or deleted
                await db.execute(
                    update(ImprovementFeedback)
                    .where(ImprovementFeedback.id == fb.id)
                    .values(status="duplicate", resolved_at=datetime.now(timezone.utc))
                )
                stats["stale"] += 1
                continue

            story = (await db.execute(
                select(Story).where(Story.id == article.story_id)
            )).scalar_one_or_none()
            if not story:
                stats["stale"] += 1
                continue

            try:
                prompt = prompt_template.format(
                    story_title=(story.title_fa or "")[:120],
                    story_summary=(story.summary_fa or "")[:400],
                    article_title=(article.title_fa or article.title_original or "")[:120],
                    article_excerpt=(article.content_fa or article.content_original or "")[:600],
                )
                params = build_openai_params(
                    model=settings.translation_model,
                    prompt=prompt,
                    max_tokens=120,
                    temperature=0.1,
                )
                response = await client.chat.completions.create(**params)
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="feedback.niloofar_audit",
                    usage=response.usage,
                )
                output = (response.choices[0].message.content or "").strip()
                first_line = output.split("\n", 1)[0].strip().lower()
                explanation = output.split("\n", 1)[1].strip()[:400] if "\n" in output else ""

                if first_line.startswith("agree"):
                    await db.execute(
                        update(Article)
                        .where(Article.id == article_uuid, Article.story_id == story.id)
                        .values(story_id=None)
                    )
                    await db.execute(
                        update(ImprovementFeedback)
                        .where(ImprovementFeedback.id == fb.id)
                        .values(
                            status="in_progress",
                            orphaned_from_story_id=story.id,
                            admin_notes=f"Niloofar agreed: {explanation}",
                            resolved_at=datetime.now(timezone.utc),
                        )
                    )
                    await _log_event(
                        db,
                        event_type="feedback_niloofar_orphan",
                        actor="niloofar",
                        story_id=story.id,
                        article_id=article_uuid,
                        signals={"explanation": explanation[:200]},
                    )
                    stats["agreed"] += 1
                elif first_line.startswith("disagree"):
                    await db.execute(
                        update(ImprovementFeedback)
                        .where(ImprovementFeedback.id == fb.id)
                        .values(
                            status="wont_do",
                            admin_notes=f"Niloofar disagreed: {explanation}",
                            resolved_at=datetime.now(timezone.utc),
                        )
                    )
                    await _log_event(
                        db,
                        event_type="feedback_niloofar_dismiss",
                        actor="niloofar",
                        story_id=story.id,
                        article_id=article_uuid,
                        signals={"explanation": explanation[:200]},
                    )
                    stats["disagreed"] += 1
                else:
                    stats["ambiguous"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"Niloofar feedback audit failed for fb {fb.id}: {e}")

        await db.commit()

    if any(v for k, v in stats.items() if k != "ambiguous"):
        logger.info(f"Niloofar feedback audit: {stats}")
    return stats


async def step_source_trust_recompute():
    """Auto-tune Source.cluster_quality_score from feedback signals.

    For each source, compute the 30d *flag rate*:
      flagged = articles with any negative is_relevant rater_feedback OR
                wrong_clustering ImprovementFeedback (status≠open)
      total   = articles ingested in the last 30 days
      rate    = flagged / total

    Sources with rate > 3 × the global median (across sources with
    ≥10 articles in window) get penalized:

      score = max(0.5, 1.0 - 2 × (rate - median))

    Sources at or below the median recover toward 1.0 by +0.05/day so
    a one-bad-week dip auto-heals. Score is then used by the matcher:
    effective_threshold = base_threshold / score, so a 0.5-trust source
    needs cosine ≥ 0.90 instead of 0.45 to attach.

    Logs source_trust_change story_event whenever a score moves > 0.05.
    """
    from sqlalchemy import select, update, func
    from app.database import async_session
    from app.models.article import Article
    from app.models.feedback import RaterFeedback
    from app.models.improvement import ImprovementFeedback
    from app.models.source import Source
    from app.services.events import log_event as _log_event

    stats = {"sources_checked": 0, "penalized": 0, "recovered": 0, "median_rate": 0.0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    async with async_session() as db:
        # Total articles per source in window
        totals_q = await db.execute(
            select(Article.source_id, func.count(Article.id))
            .where(Article.ingested_at >= cutoff)
            .group_by(Article.source_id)
        )
        totals = {sid: cnt for sid, cnt in totals_q.all()}

        # Flagged articles per source: rater rejections
        rater_flagged_q = await db.execute(
            select(Article.source_id, func.count(func.distinct(Article.id)))
            .join(RaterFeedback, RaterFeedback.article_id == Article.id)
            .where(
                Article.ingested_at >= cutoff,
                RaterFeedback.feedback_type == "article_relevance",
                RaterFeedback.is_relevant.is_(False),
            )
            .group_by(Article.source_id)
        )
        rater_flagged = {sid: cnt for sid, cnt in rater_flagged_q.all()}

        # Flagged via anonymous orphans (acted-on rows have status≠open)
        anon_flagged_q = await db.execute(
            select(Article.source_id, func.count(func.distinct(Article.id)))
            .join(
                ImprovementFeedback,
                ImprovementFeedback.target_id == func.cast(Article.id, type_=ImprovementFeedback.target_id.type),
            )
            .where(
                Article.ingested_at >= cutoff,
                ImprovementFeedback.target_type == "article",
                ImprovementFeedback.issue_type == "wrong_clustering",
                ImprovementFeedback.status != "open",
            )
            .group_by(Article.source_id)
        )
        anon_flagged = {sid: cnt for sid, cnt in anon_flagged_q.all()}

        # #3 — pull source created_at so probation-aged sources are
        # excluded from the median calc. They'd otherwise spike or
        # depress the median based on a tiny denominator and 0-1 weeks
        # of behavior, which is noise.
        source_age_q = await db.execute(select(Source.id, Source.created_at))
        source_created: dict[uuid.UUID, datetime | None] = dict(source_age_q.all())
        probation_floor = datetime.now(timezone.utc) - timedelta(days=30)

        # Compute rates
        rates: dict[uuid.UUID, float] = {}
        eligible_for_median: list[float] = []
        for sid, total in totals.items():
            if total < 10:
                continue
            flagged = rater_flagged.get(sid, 0) + anon_flagged.get(sid, 0)
            rate = flagged / total
            rates[sid] = rate
            created = source_created.get(sid)
            # Exclude sources <30d old from the median calculation. Their
            # rates are still computed and applied to themselves; only the
            # population statistic uses stable sources.
            if created and created >= probation_floor:
                continue
            eligible_for_median.append(rate)

        if not eligible_for_median:
            logger.info("Source trust: no eligible sources with ≥10 articles in 30d")
            return stats

        eligible_for_median.sort()
        median_rate = eligible_for_median[len(eligible_for_median) // 2]
        stats["median_rate"] = round(median_rate, 4)

        # Apply scores
        sources_q = await db.execute(select(Source))
        sources = list(sources_q.scalars().all())

        for source in sources:
            stats["sources_checked"] += 1
            old_score = source.cluster_quality_score or 1.0
            rate = rates.get(source.id)

            if rate is None:
                # Insufficient data — drift back toward 1.0
                new_score = min(1.0, old_score + 0.05)
            elif rate > 3 * max(median_rate, 0.01):
                # Penalize proportional to excess
                new_score = max(0.5, 1.0 - 2 * (rate - median_rate))
                stats["penalized"] += 1
            else:
                # At or below the bar — recover
                new_score = min(1.0, old_score + 0.05)
                if new_score > old_score:
                    stats["recovered"] += 1

            new_score = round(new_score, 3)
            if abs(new_score - old_score) > 0.005:
                await db.execute(
                    update(Source)
                    .where(Source.id == source.id)
                    .values(cluster_quality_score=new_score)
                )
                # Log significant moves only (≥0.05) to avoid event spam
                if abs(new_score - old_score) >= 0.05:
                    await _log_event(
                        db,
                        event_type="source_trust_change",
                        actor="maintenance",
                        signals={
                            "source_id": str(source.id),
                            "source_slug": source.slug,
                            "old_score": old_score,
                            "new_score": new_score,
                            "flag_rate_30d": round(rate or 0.0, 4),
                            "median_rate_30d": round(median_rate, 4),
                        },
                    )
                    logger.info(
                        f"  Source trust: {source.slug} {old_score:.3f} → {new_score:.3f} "
                        f"(rate={rate or 0:.3f}, median={median_rate:.3f})"
                    )

        await db.commit()

    logger.info(f"Source trust recompute: {stats}")
    return stats


async def step_age_out_stale_feedback():
    """#9 — age out anonymous feedback that never reached consensus.

    Anonymous wrong_clustering improvements that sit in "open" status
    for >14 days without hitting the 3-identity threshold are
    effectively rejected by collective inaction. Mark them
    `wont_do` with reason "stale_unconverged" and emit
    feedback_rejected_threshold so /dashboard/learning can show them
    as a separate failure mode (vs Niloofar dismissals).

    Cheap pure SQL — runs every full cron at 04:00 UTC.
    """
    from sqlalchemy import select, update, func, distinct
    from app.database import async_session
    from app.models.improvement import ImprovementFeedback
    from app.services.events import log_event as _log_event

    stats = {"aged": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    async with async_session() as db:
        identity_expr = func.coalesce(
            ImprovementFeedback.submitter_cookie,
            ImprovementFeedback.submitter_fingerprint,
        )
        # Per (target_id) voter counts, restricted to wrong_clustering opens.
        groups = (await db.execute(
            select(
                ImprovementFeedback.target_id,
                func.count(distinct(identity_expr)).label("voters"),
            )
            .where(
                ImprovementFeedback.target_type == "article",
                ImprovementFeedback.issue_type == "wrong_clustering",
                ImprovementFeedback.status == "open",
                ImprovementFeedback.created_at < cutoff,
            )
            .group_by(ImprovementFeedback.target_id)
            .having(func.count(distinct(identity_expr)) < 3)
        )).all()

        for target_id, voters in groups:
            if not target_id:
                continue
            # Mark every row of this target as wont_do.
            res = await db.execute(
                update(ImprovementFeedback)
                .where(
                    ImprovementFeedback.target_type == "article",
                    ImprovementFeedback.target_id == target_id,
                    ImprovementFeedback.issue_type == "wrong_clustering",
                    ImprovementFeedback.status == "open",
                )
                .values(
                    status="wont_do",
                    admin_notes="Aged out: did not reach 3-identity threshold within 14 days.",
                    resolved_at=datetime.now(timezone.utc),
                )
            )
            stats["aged"] += int(res.rowcount or 0)
            try:
                article_uuid = uuid.UUID(target_id)
            except ValueError:
                continue
            await _log_event(
                db,
                event_type="feedback_rejected_threshold",
                actor="maintenance",
                article_id=article_uuid,
                signals={"voters": int(voters), "window_days": 14},
            )
        await db.commit()

    if stats["aged"]:
        logger.info(f"Aged-out unconverged feedback: {stats}")
    return stats


async def step_source_trust_fast():
    """F8 — fast hourly path for source trust.

    Cheaper than step_source_trust_recompute (no global median calc,
    no full source scan). Only acts on sources that received a new
    negative flag within the last 60 minutes. For each such source,
    if the recent 24h flag rate exceeds 3× the source's own 30d
    historical rate, apply a one-step penalty cap of 0.85 immediately
    instead of waiting for the 04:00 UTC daily pass.

    Recovery is intentionally NOT done here — only the daily pass
    rebuilds. This keeps the loop biased toward catching new bad
    behavior fast, not erasing it.

    Pure SQL, no LLM. Runs in ~50ms even with 100+ sources.
    """
    from sqlalchemy import select, func, update
    from app.database import async_session
    from app.models.article import Article
    from app.models.feedback import RaterFeedback
    from app.models.improvement import ImprovementFeedback
    from app.models.source import Source
    from app.services.events import log_event as _log_event

    stats = {"sources_touched": 0, "fast_penalized": 0}
    now = datetime.now(timezone.utc)
    last_hour = now - timedelta(hours=1)
    last_day = now - timedelta(hours=24)
    historical = now - timedelta(days=30)

    async with async_session() as db:
        # Sources with a new flag in the last hour. Two paths: rater
        # rejections + anonymous wrong_clustering improvements.
        recent_rater = await db.execute(
            select(func.distinct(Article.source_id))
            .join(RaterFeedback, RaterFeedback.article_id == Article.id)
            .where(
                RaterFeedback.created_at >= last_hour,
                RaterFeedback.feedback_type == "article_relevance",
                RaterFeedback.is_relevant.is_(False),
            )
        )
        recent_anon = await db.execute(
            select(func.distinct(Article.source_id))
            .join(
                ImprovementFeedback,
                ImprovementFeedback.target_id == func.cast(Article.id, type_=ImprovementFeedback.target_id.type),
            )
            .where(
                ImprovementFeedback.created_at >= last_hour,
                ImprovementFeedback.target_type == "article",
                ImprovementFeedback.issue_type == "wrong_clustering",
            )
        )
        touched_ids = {sid for sid, in recent_rater.all() if sid} | {sid for sid, in recent_anon.all() if sid}

        if not touched_ids:
            return stats
        stats["sources_touched"] = len(touched_ids)

        for source_id in touched_ids:
            # 24h vs 30d rate, on this source's own articles.
            denom_24h = (await db.execute(
                select(func.count(Article.id)).where(
                    Article.source_id == source_id,
                    Article.ingested_at >= last_day,
                )
            )).scalar() or 0
            if denom_24h < 5:
                continue  # need a meaningful denominator
            num_24h = (await db.execute(
                select(func.count(func.distinct(Article.id)))
                .join(RaterFeedback, RaterFeedback.article_id == Article.id, isouter=True)
                .where(
                    Article.source_id == source_id,
                    Article.ingested_at >= last_day,
                    RaterFeedback.feedback_type == "article_relevance",
                    RaterFeedback.is_relevant.is_(False),
                )
            )).scalar() or 0
            rate_24h = num_24h / denom_24h

            denom_30d = (await db.execute(
                select(func.count(Article.id)).where(
                    Article.source_id == source_id,
                    Article.ingested_at >= historical,
                )
            )).scalar() or 0
            num_30d = (await db.execute(
                select(func.count(func.distinct(Article.id)))
                .join(RaterFeedback, RaterFeedback.article_id == Article.id, isouter=True)
                .where(
                    Article.source_id == source_id,
                    Article.ingested_at >= historical,
                    RaterFeedback.feedback_type == "article_relevance",
                    RaterFeedback.is_relevant.is_(False),
                )
            )).scalar() or 0
            rate_30d = (num_30d / denom_30d) if denom_30d else 0.0

            # Fire when 24h rate is ≥3× historical and exceeds 0.10 absolute
            # (otherwise tiny denominators trigger nuisance penalties).
            if rate_24h >= max(0.10, 3 * rate_30d):
                src = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
                if not src:
                    continue
                old_score = src.cluster_quality_score or 1.0
                new_score = round(min(old_score, 0.85), 3)
                if new_score < old_score - 0.005:
                    await db.execute(
                        update(Source).where(Source.id == source_id).values(cluster_quality_score=new_score)
                    )
                    await _log_event(
                        db,
                        event_type="source_trust_fast_penalty",
                        actor="hourly_cron",
                        signals={
                            "source_id": str(source_id),
                            "source_slug": src.slug,
                            "old_score": old_score,
                            "new_score": new_score,
                            "rate_24h": round(rate_24h, 4),
                            "rate_30d": round(rate_30d, 4),
                        },
                    )
                    stats["fast_penalized"] += 1

        await db.commit()

    if stats["fast_penalized"]:
        logger.info(f"Source trust fast: {stats}")
    return stats


async def step_extract_analyst_takes():
    """Extract structured analyst takes from Telegram posts.

    For each analyst with a telegram_handle, finds their channel's unprocessed
    posts, uses the LLM to match each post to a story and extract:
    - summary_fa: a concise Persian summary of the argument
    - key_claim: the main claim in one sentence
    - take_type: prediction | reasoning | insider_signal | fact_check | historical_parallel | commentary
    - confidence_direction: bullish | bearish | neutral

    Only processes posts that don't already have an AnalystTake record.
    """
    import json as _json

    from sqlalchemy import select

    from app.config import settings
    from app.database import async_session
    from app.models.analyst import Analyst
    from app.models.analyst_take import AnalystTake
    from app.models.social import TelegramChannel, TelegramPost
    from app.models.story import Story

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping analyst take extraction")
        return {"skipped": "no_openai_key"}

    stats = {"processed": 0, "matched": 0, "failed": 0, "no_match": 0}

    async with async_session() as db:
        # 1. Get all analysts with a telegram_handle
        analyst_result = await db.execute(
            select(Analyst).where(
                Analyst.telegram_handle.isnot(None),
                Analyst.is_active.is_(True),
            )
        )
        analysts = list(analyst_result.scalars().all())
        if not analysts:
            logger.info("No analysts with telegram_handle — skipping")
            return stats

        # Build mapping: telegram_handle (lowered, no @) -> analyst
        handle_to_analyst: dict[str, Analyst] = {}
        for a in analysts:
            handle = a.telegram_handle.lstrip("@").lower()
            handle_to_analyst[handle] = a

        if not handle_to_analyst:
            return stats

        # 2. Find telegram channels matching analyst handles
        channel_result = await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.is_active.is_(True),
            )
        )
        channels = list(channel_result.scalars().all())

        # Map channel_id -> analyst for channels that belong to an analyst
        channel_to_analyst: dict = {}
        for ch in channels:
            ch_username = ch.username.lstrip("@").lower()
            if ch_username in handle_to_analyst:
                channel_to_analyst[ch.id] = handle_to_analyst[ch_username]

        if not channel_to_analyst:
            logger.info("No telegram channels match analyst handles — skipping")
            return stats

        # 3. Get posts from those channels that don't have an AnalystTake yet
        existing_post_ids_result = await db.execute(
            select(AnalystTake.telegram_post_id).where(
                AnalystTake.telegram_post_id.isnot(None)
            )
        )
        existing_post_ids = {row[0] for row in existing_post_ids_result.all()}

        posts_result = await db.execute(
            select(TelegramPost)
            .where(
                TelegramPost.channel_id.in_(list(channel_to_analyst.keys())),
                TelegramPost.text.isnot(None),
            )
            .order_by(TelegramPost.date.desc())
            .limit(200)  # cap per run
        )
        posts = [p for p in posts_result.scalars().all() if p.id not in existing_post_ids]

        if not posts:
            logger.info("No new analyst posts to process")
            return stats

        # 4. Get current story titles for matching
        story_result = await db.execute(
            select(Story)
            .where(Story.article_count >= 3)
            .order_by(Story.trending_score.desc())
            .limit(50)
        )
        stories = list(story_result.scalars().all())
        story_list_text = "\n".join(
            f"{i+1}. [{str(s.id)[:8]}] {s.title_fa or s.title_en or '(no title)'}"
            for i, s in enumerate(stories)
        )
        story_id_map = {str(s.id)[:8]: s.id for s in stories}

        # 5. Process each post with LLM
        from openai import OpenAI
        from app.services.llm_helper import build_openai_params

        client = OpenAI(api_key=settings.openai_api_key)

        EXTRACT_PROMPT = """You are analyzing a Telegram post by an Iranian political analyst.

Given the post text and a list of current news stories, extract:
1. story_match: The short ID (8 chars in brackets) of the most relevant story, or "none" if no match
2. summary_fa: A 1-2 sentence Persian summary of the analyst's argument (max 200 chars)
3. key_claim: The main claim in one Persian sentence (max 150 chars), or null
4. take_type: One of: prediction, reasoning, insider_signal, fact_check, historical_parallel, commentary
5. confidence_direction: bullish (optimistic about outcome), bearish (pessimistic), or neutral

Return ONLY valid JSON with these 5 keys. No markdown, no explanation.

Current stories:
{stories}

Analyst post:
{post_text}"""

        for post in posts:
            analyst = channel_to_analyst.get(post.channel_id)
            if not analyst:
                continue

            post_text = (post.text or "")[:2000]
            if len(post_text.strip()) < 20:
                continue  # skip very short posts

            try:
                prompt = EXTRACT_PROMPT.format(
                    stories=story_list_text,
                    post_text=post_text,
                )
                params = build_openai_params(
                    model=settings.bias_scoring_model,
                    prompt=prompt,
                    max_tokens=500,
                    temperature=0.2,
                )
                resp = client.chat.completions.create(**params)
                from app.services.llm_usage import log_llm_usage
                await log_llm_usage(
                    model=settings.bias_scoring_model,
                    purpose="analyst_takes.extract",
                    usage=resp.usage,
                )
                raw_response = resp.choices[0].message.content.strip()

                # Clean markdown fences if present
                if raw_response.startswith("```"):
                    raw_response = re.sub(r"^```(?:json)?\s*", "", raw_response)
                    raw_response = re.sub(r"\s*```$", "", raw_response)

                data = _json.loads(raw_response)

                # Resolve story match
                matched_story_id = None
                story_match = data.get("story_match", "none")
                if story_match and story_match != "none":
                    matched_story_id = story_id_map.get(story_match)

                take = AnalystTake(
                    analyst_id=analyst.id,
                    story_id=matched_story_id,
                    telegram_post_id=post.id,
                    raw_text=post_text,
                    summary_fa=str(data.get("summary_fa", ""))[:500] or None,
                    key_claim=str(data.get("key_claim", ""))[:300] or None,
                    take_type=data.get("take_type", "commentary"),
                    confidence_direction=data.get("confidence_direction"),
                    published_at=post.date,
                )
                db.add(take)
                stats["processed"] += 1
                if matched_story_id:
                    stats["matched"] += 1
                else:
                    stats["no_match"] += 1

            except Exception as e:
                logger.warning(f"Failed to extract analyst take from post {post.id}: {e}")
                stats["failed"] += 1

        await db.commit()

    if stats["processed"] > 0:
        logger.info(
            f"Analyst takes: {stats['processed']} extracted, "
            f"{stats['matched']} matched to stories, "
            f"{stats['no_match']} unmatched, "
            f"{stats['failed']} failed"
        )
    return stats


async def step_verify_predictions():
    """Verify analyst predictions against what actually happened.

    Finds AnalystTake records where:
    - take_type = "prediction"
    - verified_later IS NULL (not yet checked)
    - published_at > 3 days ago (give predictions time to play out)

    Uses the nano model to compare the prediction's key_claim against
    the story's current summary, then updates verified_later (bool)
    and verification_note.

    Max 5 verifications per run to keep costs minimal.
    """
    import json as _json

    import openai
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.analyst_take import AnalystTake
    from app.models.story import Story

    if not settings.openai_api_key:
        logger.warning("Verify predictions: OPENAI_API_KEY not set, skipping")
        return {"verified": 0, "skipped_no_key": True}

    MAX_PER_RUN = 5
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    stats = {"verified": 0, "correct": 0, "incorrect": 0, "inconclusive": 0, "failed": 0}

    async with async_session() as db:
        result = await db.execute(
            select(AnalystTake)
            .options(selectinload(AnalystTake.story))
            .where(
                AnalystTake.take_type == "prediction",
                AnalystTake.verified_later.is_(None),
                AnalystTake.published_at.isnot(None),
                AnalystTake.published_at < cutoff,
                AnalystTake.key_claim.isnot(None),
                AnalystTake.story_id.isnot(None),
            )
            .order_by(AnalystTake.published_at.asc())
            .limit(MAX_PER_RUN)
        )
        predictions = list(result.scalars().all())

        if not predictions:
            logger.info("Verify predictions: no pending predictions to check")
            return stats

        logger.info(f"Verifying {len(predictions)} analyst predictions...")

        from app.services.llm_helper import build_openai_params
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        for take in predictions:
            story = take.story
            if not story or not story.summary_fa:
                # Story doesn't have a summary yet — skip, will retry next run
                continue

            prompt = (
                "یک تحلیلگر پیش‌بینی زیر را کرده بود:\n"
                f"پیش‌بینی: {take.key_claim}\n\n"
                f"آنچه واقعاً اتفاق افتاد (خلاصه فعلی خبر):\n{story.summary_fa[:500]}\n\n"
                "آیا این پیش‌بینی درست بود؟ فقط JSON برگردان:\n"
                '{"correct": true/false/null, "note": "<توضیح کوتاه فارسی ۱ جمله>"}\n'
                "اگر هنوز مشخص نیست null بگذار."
            )

            try:
                params = build_openai_params(
                    model=settings.translation_model,  # nano — cheapest
                    prompt=prompt,
                    max_tokens=256,
                    temperature=0,
                )
                response = await client.chat.completions.create(**params)
                from app.services.llm_usage import log_llm_usage
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="predictions.verify",
                    usage=response.usage,
                    story_id=story.id,
                )
                text = response.choices[0].message.content.strip()

                # Parse JSON
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()

                parsed = _json.loads(text)
                correct = parsed.get("correct")
                note = parsed.get("note", "")

                if correct is None:
                    # Inconclusive — leave verified_later as None, add note
                    take.verification_note = f"بررسی شد — هنوز مشخص نیست: {note}"
                    stats["inconclusive"] += 1
                else:
                    take.verified_later = bool(correct)
                    take.verification_note = note
                    if correct:
                        stats["correct"] += 1
                    else:
                        stats["incorrect"] += 1

                stats["verified"] += 1
                await db.commit()
                logger.info(
                    f"  ✓ Prediction verified: correct={correct} — "
                    f"{(take.key_claim or '')[:50]}"
                )

            except Exception as e:
                logger.warning(f"  ✗ Failed to verify prediction {take.id}: {e}")
                stats["failed"] += 1
                await db.rollback()

    logger.info(
        f"Prediction verification: {stats['verified']} verified "
        f"({stats['correct']} correct, {stats['incorrect']} incorrect, "
        f"{stats['inconclusive']} inconclusive), {stats['failed']} failed"
    )
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


async def step_prune_stagnant():
    """Delete small stories that have stopped growing.

    Two tiers, both targeting stories that will never reach the
    article_count ≥ 5 visibility threshold:

    - 1-article stories older than 48h → these are one-offs that no other
      source picked up. They bloat the hidden-story count without ever
      surfacing. The article gets unlinked (returns to orphan pool) and
      the story row is deleted.
    - 2-4 article stories older than 14 days → a story that has been
      stable at 2-4 for two weeks is not coming back. Same treatment.

    Runs before step_archive_stale so the 60-day sweep doesn't also
    re-process these rows. Idempotent — a second run is a no-op once the
    small-stagnant set is empty.
    """
    from sqlalchemy import select, update, delete, text as _sql
    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article

    stats = {"singles_pruned": 0, "smalls_pruned": 0, "skipped_with_dependents": 0}
    now = datetime.now(timezone.utc)
    singles_cutoff = now - timedelta(hours=48)
    smalls_cutoff = now - timedelta(days=14)

    async def _delete_stories_safe(db, story_ids: list) -> int:
        """Delete stories after clearing nullable references and skipping any
        that have non-nullable dependents (social_sentiment_snapshots,
        story_events). Mirrors the prune-noise guard pattern.
        """
        if not story_ids:
            return 0
        # Null nullable FKs first — articles, telegram_posts, rater_feedback,
        # analyst_takes all have nullable story_id and represent data we want
        # to keep even if the host story goes away.
        await db.execute(_sql(
            "UPDATE articles        SET story_id = NULL WHERE story_id = ANY(:ids)"
        ), {"ids": story_ids})
        await db.execute(_sql(
            "UPDATE telegram_posts  SET story_id = NULL WHERE story_id = ANY(:ids)"
        ), {"ids": story_ids})
        await db.execute(_sql(
            "UPDATE rater_feedback  SET story_id = NULL WHERE story_id = ANY(:ids)"
        ), {"ids": story_ids})
        await db.execute(_sql(
            "UPDATE analyst_takes   SET story_id = NULL WHERE story_id = ANY(:ids)"
        ), {"ids": story_ids})
        # Self-FK cleanup — a child story may point back via split_from_id.
        await db.execute(_sql(
            "UPDATE stories         SET split_from_id = NULL WHERE split_from_id = ANY(:ids)"
        ), {"ids": story_ids})
        # NOT NULL FKs — skip any story still referenced from the audit log
        # (story_events) or sentiment snapshots. We never delete those rows
        # because they're history we want to preserve.
        result = await db.execute(_sql("""
            DELETE FROM stories
            WHERE id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM story_events                WHERE story_id = stories.id)
              AND NOT EXISTS (SELECT 1 FROM social_sentiment_snapshots  WHERE story_id = stories.id)
        """), {"ids": story_ids})
        return getattr(result, "rowcount", 0) or 0

    async with async_session() as db:
        # Tier 1 — 1-article stories >48h
        singles = (await db.execute(
            select(Story.id).where(
                Story.article_count == 1,
                Story.last_updated_at < singles_cutoff,
                Story.is_edited.is_(False),
            )
        )).scalars().all()
        deleted = await _delete_stories_safe(db, list(singles))
        stats["singles_pruned"] = deleted
        stats["skipped_with_dependents"] += len(singles) - deleted

        # Tier 2 — 2-4 article stories >14 days with no recent updates
        smalls = (await db.execute(
            select(Story.id).where(
                Story.article_count.between(2, 4),
                Story.last_updated_at < smalls_cutoff,
                Story.is_edited.is_(False),
            )
        )).scalars().all()
        deleted = await _delete_stories_safe(db, list(smalls))
        stats["smalls_pruned"] = deleted
        stats["skipped_with_dependents"] += len(smalls) - deleted

        await db.commit()

    if stats["singles_pruned"] or stats["smalls_pruned"]:
        logger.info(f"Prune stagnant: {stats}")
    return stats


async def step_demote_umbrella_stories():
    """Auto-demote stories that grew into umbrellas.

    Pattern: first_published_at >21d ago, article_count >100, and
    last_updated_at recent (the cluster keeps absorbing adjacent
    topics every day so it never appears stale by F2/F3 metrics).
    These stories dominate the homepage with month-old context
    re-stamped as fresh — exactly what F1/F2/F3/F4 were meant to
    prevent but couldn't catch because the wall-clock signals all
    say "current."

    Action: set priority = -50 so trending pushes them off the
    homepage; clustering's umbrella-cap (clustering.py
    UMBRELLA_FIRST_PUB_CAP_DAYS) prevents further growth. Emits
    `story_umbrella_demoted` event.

    Conservative thresholds:
      - first_published_at < now - 21 days
      - article_count > 100
      - priority > -10  (skip already-demoted)
    """
    from sqlalchemy import select, update
    from app.database import async_session
    from app.models.story import Story
    from app.services.events import log_event as _log_event

    stats = {"checked": 0, "demoted": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=21)

    async with async_session() as db:
        rows = (await db.execute(
            select(Story).where(
                Story.first_published_at < cutoff,
                Story.article_count > 100,
                Story.priority > -10,
                Story.archived_at.is_(None),
            )
        )).scalars().all()
        stats["checked"] = len(rows)
        for s in rows:
            await db.execute(
                update(Story).where(Story.id == s.id).values(priority=-50)
            )
            await _log_event(
                db,
                event_type="story_umbrella_demoted",
                actor="maintenance",
                story_id=s.id,
                signals={
                    "article_count": int(s.article_count or 0),
                    "first_published_at": s.first_published_at.isoformat() if s.first_published_at else None,
                    "title_fa": (s.title_fa or "")[:120],
                },
            )
            stats["demoted"] += 1
            logger.info(f"  Umbrella demote: {s.title_fa[:60] if s.title_fa else s.id} ({s.article_count} articles)")
        await db.commit()
    if stats["demoted"]:
        logger.info(f"Umbrella demote: {stats}")
    return stats


async def step_archive_stale():
    """Three-tier story aging.

    0) **Auto-freeze at 7d** — any story whose last_updated_at is
       older than 7 days gets `frozen_at` set. Frozen stories no
       longer accept new articles via clustering and are skipped by
       guardrail/edit flows that respect frozen_at. Story stays
       visible; archive (tier 1) handles homepage filtering.

    1) **Soft-archive at 30d** — any story whose last_updated_at is
       outside the 30-day relevance window gets `archived_at` set.
       Archived stories are filtered out of /api/v1/stories/trending,
       /blindspots, the homepage picks, and clustering candidate
       lists. Direct URLs continue to render (SEO / permalinks).

    2) **Hard-delete tiny stories at 60d** — long-tail rows with
       <3 articles and no updates in 60 days get removed entirely.
       Their articles are unlinked back into the orphan pool so a
       fresh cluster pass can give them a real home if newer
       siblings have arrived.

    Also recounts article_count / source_count for non-archived
    stories so the homepage reflects reality after merges/splits.
    """
    from sqlalchemy import select, update, func, delete

    from app.database import async_session
    from app.models.story import Story
    from app.models.article import Article
    from app.services.events import log_event as _log_event

    stats = {"auto_frozen": 0, "soft_archived": 0, "hard_deleted": 0, "recounted": 0}
    now = datetime.now(timezone.utc)
    freeze_cutoff = now - timedelta(days=7)
    soft_cutoff = now - timedelta(days=30)
    hard_cutoff = now - timedelta(days=60)

    async with async_session() as db:
        # Tier 0 — auto-freeze stories idle for >7 days. Stops further
        # article accretion and HITL guardrail churn on stories that
        # are effectively over.
        freeze_result = await db.execute(
            select(Story).where(
                Story.frozen_at.is_(None),
                Story.last_updated_at < freeze_cutoff,
            )
        )
        for story in freeze_result.scalars().all():
            story.frozen_at = now
            await _log_event(
                db,
                event_type="story_auto_frozen",
                actor="maintenance",
                story_id=story.id,
                signals={
                    "last_updated_at": story.last_updated_at.isoformat() if story.last_updated_at else None,
                    "article_count": int(story.article_count or 0),
                    "title_fa": (story.title_fa or "")[:120],
                    "reason": "idle_7d",
                },
            )
            stats["auto_frozen"] += 1

        # Tier 1 — soft-archive everything older than 30d that isn't
        # already archived. last_updated_at is the anchor (matches the
        # F2 trending decay), with a fall-through to first_published_at
        # for stories that somehow lack last_updated_at.
        soft_result = await db.execute(
            select(Story).where(
                Story.archived_at.is_(None),
                Story.last_updated_at < soft_cutoff,
            )
        )
        for story in soft_result.scalars().all():
            story.archived_at = now
            stats["soft_archived"] += 1

        # Tier 2 — delete tiny stale stories. Mirror the FK-safe pattern
        # from step_prune_stagnant: clear all nullable references first,
        # then delete only stories with no audit/snapshot rows still
        # pointing at them. Without this guard the DELETE raises
        # ForeignKeyViolationError exactly like prune-stagnant did
        # before the 2026-04-28 fix.
        from sqlalchemy import text as _safe_t
        result = await db.execute(
            select(Story.id).where(
                Story.last_updated_at < hard_cutoff,
                Story.article_count < 3,
            )
        )
        stale_ids = [row[0] for row in result.all()]
        if stale_ids:
            for table, col in (
                ("articles", "story_id"),
                ("telegram_posts", "story_id"),
                ("rater_feedback", "story_id"),
                ("analyst_takes", "story_id"),
                ("stories", "split_from_id"),
            ):
                await db.execute(_safe_t(
                    f"UPDATE {table} SET {col} = NULL WHERE {col} = ANY(:ids)"
                ), {"ids": stale_ids})
            del_result = await db.execute(_safe_t("""
                DELETE FROM stories
                WHERE id = ANY(:ids)
                  AND NOT EXISTS (SELECT 1 FROM story_events WHERE story_id = stories.id)
                  AND NOT EXISTS (SELECT 1 FROM social_sentiment_snapshots WHERE story_id = stories.id)
            """), {"ids": stale_ids})
            stats["hard_deleted"] = del_result.rowcount or 0
            stats["hard_skipped_with_history"] = len(stale_ids) - stats["hard_deleted"]

        # Recount article_count for ALL stories (in case articles were added/removed)
        result = await db.execute(select(Story).where(Story.article_count >= 1))
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

    if stats["auto_frozen"] > 0 or stats["soft_archived"] > 0 or stats["hard_deleted"] > 0 or stats["recounted"] > 0:
        logger.info(f"Archive/recount: {stats}")
    return stats


async def step_recalculate_trending():
    """Recalculate trending scores for all visible stories."""
    from sqlalchemy import select, text

    from app.database import async_session
    from app.models.story import Story

    stats = {"updated": 0, "first_published_backfilled": 0}

    async with async_session() as db:
        # Heal any story whose first_published_at is stale or null. The
        # per-merge path in _refresh_story_metadata fixes this going
        # forward; this UPDATE backfills history and protects against
        # any future code path that forgets.
        backfill = await db.execute(text("""
            UPDATE stories s
            SET first_published_at = sub.min_pub
            FROM (
                SELECT story_id, MIN(published_at) AS min_pub
                FROM articles
                WHERE published_at IS NOT NULL AND story_id IS NOT NULL
                GROUP BY story_id
            ) sub
            WHERE s.id = sub.story_id
              AND s.first_published_at IS DISTINCT FROM sub.min_pub
        """))
        stats["first_published_backfilled"] = backfill.rowcount or 0
        await db.commit()

        # F2 — continuous decay anchored on last_updated_at.
        # The site's editorial intent: stories matter most for ~7 days,
        # are dated after ~14, and dead by 30. The previous formula
        # decayed linearly from first_published_at over 30d, so a story
        # that gained a fresh article on day 25 still scored low. Anchor
        # on last_updated_at instead so a refreshed story behaves like
        # a young one.
        #
        # Score = article_count * 0.85^days_since_last_update.
        # Day 0: full score. Day 7: 32% of articles. Day 14: 10%.
        # Day 30: ~1%. Combined with archive_at gating elsewhere, this
        # naturally pushes old content off the homepage without explicit
        # cutoffs in every consumer.
        result = await db.execute(
            select(Story).where(
                Story.article_count >= 5,
                Story.archived_at.is_(None),
            )
        )
        now_utc = datetime.now(timezone.utc)
        for story in result.scalars().all():
            old_score = story.trending_score
            anchor = story.last_updated_at or story.first_published_at
            if anchor:
                days_ago = (now_utc - anchor).total_seconds() / 86400.0
                recency = 0.85 ** max(0.0, days_ago)
                # Floor so a 30+ day story without an anchor doesn't
                # math.expDown to zero and drop entirely from
                # admin-facing /api/v1/stories listings.
                recency = max(recency, 0.005)
            else:
                recency = 0.05
            story.trending_score = story.article_count * recency
            if abs(story.trending_score - old_score) > 0.1:
                stats["updated"] += 1

        await db.commit()

    if stats["updated"] > 0:
        logger.info(f"Trending recalc: {stats['updated']} stories updated")
    return stats


async def step_telegram_link_posts():
    """Link unlinked Telegram posts to stories via embedding similarity."""
    from app.database import async_session
    from app.services.telegram_analysis import link_posts_by_embedding

    async with async_session() as db:
        stats = await link_posts_by_embedding(db, threshold=0.35)

    return stats


async def step_telegram_reassign_posts():
    """Revisit already-linked posts and move any whose best-match story
    has drifted since they were first attached."""
    from app.database import async_session
    from app.services.telegram_analysis import reassign_posts_by_embedding

    async with async_session() as db:
        stats = await reassign_posts_by_embedding(db)

    return stats


async def step_niloofar_image_rescue():
    """Niloofar picks a story image when the auto-chosen one is bad.

    The frontend picks a story's cover via _story_brief_with_extras,
    which scores each article's image_url by (is-stable-URL, title
    overlap, length) and picks the winner. That scorer is good at
    ranking but doesn't bail out when ALL candidates are bad — it
    just returns None and we fall through to the site-logo fallback,
    leaving a newspaper icon where a real photo should be.

    This step fixes that: for every story whose best available image
    is null/icon/broken-iranintl, walk the articles again with the
    stricter _is_bad_image filter and promote the first real photo
    to `manual_image_url` inside summary_en, flagging is_edited so
    the pipeline won't overwrite it.

    No LLM call — Niloofar here is "the editorial rule", not a prompt.
    Runs after fix_images so we pick up whatever R2 migration just
    landed. Capped at 200 stories per run by trending_score.
    """
    import json as _json
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.api.v1.stories import _is_bad_image

    stats = {"checked": 0, "rescued": 0, "no_candidate": 0, "already_ok": 0, "tier_promoted": 0}

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(200)
        )
        stories = list(result.scalars().all())

    for story in stories:
        stats["checked"] += 1
        # If a curator already set a manual_image_url and it's still
        # valid, leave it alone — that's an editorial decision.
        blob = {}
        if story.summary_en:
            try:
                blob = _json.loads(story.summary_en)
            except Exception:
                blob = {}
        existing_manual = blob.get("manual_image_url")
        if existing_manual and not _is_bad_image(existing_manual):
            stats["already_ok"] += 1
            continue

        # Would the frontend scorer pick a real photo on its own?
        candidates = [
            a for a in story.articles
            if a.image_url and not _is_bad_image(a.image_url)
        ]
        if not candidates:
            stats["no_candidate"] += 1
            # Promote to HITL review queue so a curator can pin a manual
            # image or hide the story. Idempotent — only writes when the
            # tier is still 0.
            from app.services.events import log_event
            async with async_session() as db:
                s = await db.get(Story, story.id)
                if s and (getattr(s, "review_tier", 0) or 0) < 1:
                    s.review_tier = 1
                    await log_event(
                        db,
                        event_type="needs_image",
                        actor="niloofar",
                        story_id=s.id,
                        new_value="review_tier=1",
                        signals={"reason": "no_real_article_image", "article_count": s.article_count},
                    )
                    await db.commit()
                    stats["tier_promoted"] += 1
            continue

        # If the automatic scorer would already pick a valid image we
        # don't need to intervene — only step in when a manual pick
        # does better. Prefer: (stable URL, title overlap, length).
        story_words = {w for w in (story.title_fa or "").split() if len(w) >= 3}

        def _score(a):
            art_words = {
                w for w in (a.title_fa or a.title_original or "").split()
                if len(w) >= 3
            }
            overlap = len(story_words & art_words)
            url = a.image_url or ""
            is_stable = url.startswith("/images/") or "r2.dev" in url or "r2.cloudflarestorage" in url
            return (1 if is_stable else 0, overlap, len(url))

        best = max(candidates, key=_score)
        # Already a valid image_url on story (auto scorer is happy)?
        # Skip writing manual_image_url so we don't accumulate no-op
        # is_edited flags on otherwise-clean stories.
        auto_ok = any(
            a.image_url and not _is_bad_image(a.image_url)
            for a in story.articles
        )
        if auto_ok and not existing_manual:
            # Auto scorer will pick a good image next page load; nothing
            # to write. `best` may differ from its pick, but "good enough
            # without an editorial flag" is the right default.
            stats["already_ok"] += 1
            continue

        async with async_session() as db:
            s = await db.get(Story, story.id)
            if not s:
                continue
            try:
                cur_blob = _json.loads(s.summary_en) if s.summary_en else {}
            except Exception:
                cur_blob = {}
            cur_blob["manual_image_url"] = best.image_url
            s.summary_en = _json.dumps(cur_blob, ensure_ascii=False)
            if hasattr(s, "is_edited"):
                s.is_edited = True
            await db.commit()
        stats["rescued"] += 1

    logger.info(f"Niloofar image rescue: {stats}")
    return stats


async def step_telegram_deep_analysis():
    """Two-pass deep LLM analysis of Telegram discourse for top stories.

    Cost guard: before running the 3-call LLM pipeline per story, we
    hash the post set and compare against the hash stored on the last
    run. If the hash matches (same posts, same texts) we skip — the
    cached analysis is still accurate. This alone eliminates ~60-80%
    of calls on a typical run, since the top-15 stories are stable
    between 4-hour maintenance passes.
    """
    import hashlib as _hashlib
    from app.database import async_session
    from app.models.social import TelegramPost
    from app.models.story import Story
    from app.services.telegram_analysis import analyze_story_telegram
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    stats = {"analyzed": 0, "skipped_unchanged": 0, "skipped_locked": 0, "skipped_no_data": 0, "errors": 0}

    # 48h maturity lock — same principle as step_summarize. Once a story
    # has been stable for this long past its last_updated_at, freeze its
    # telegram analysis too; re-runs after that rarely add signal and
    # burn Pass 2 premium tokens.
    TELEGRAM_LOCK_HOURS = 48
    # Top-5 get the premium Pass 2 model; #6-10 drop to the baseline
    # model to cut token cost without gutting the homepage's lead card.
    PREMIUM_RANK_LIMIT = 5
    # Raise the article floor: stories with <5 articles rarely have
    # enough Telegram discourse to analyze well.
    ARTICLE_COUNT_FLOOR = 5
    # Cap the per-run queue — paired with the article floor this keeps
    # daily Pass 2 calls well under the old ceiling.
    MAX_STORIES = 10

    async with async_session() as db:
        subq = (
            select(TelegramPost.story_id, func.count(TelegramPost.id).label("post_count"))
            .where(TelegramPost.story_id.isnot(None))
            .where(TelegramPost.text.isnot(None))
            .group_by(TelegramPost.story_id)
            .having(func.count(TelegramPost.id) >= 2)
            .subquery()
        )

        # Union two pools: top by trending_score (traditional) + top by
        # last_updated_at (the pool the homepage sidebar draws from).
        # Without the second pool, fresh stories never get analyzed and
        # the homepage sidebar stays empty even when the step just ran.
        # Dedup by id and cap at MAX_STORIES total.
        trending_result = await db.execute(
            select(Story.id, Story.title_fa, subq.c.post_count)
            .join(subq, Story.id == subq.c.story_id)
            .where(Story.article_count >= ARTICLE_COUNT_FLOOR)
            .where(Story.frozen_at.is_(None))
            .order_by(Story.trending_score.desc())
            .limit(MAX_STORIES)
        )
        fresh_result = await db.execute(
            select(Story.id, Story.title_fa, subq.c.post_count)
            .join(subq, Story.id == subq.c.story_id)
            .where(Story.article_count >= ARTICLE_COUNT_FLOOR)
            .where(Story.frozen_at.is_(None))
            .order_by(Story.last_updated_at.desc().nullslast())
            .limit(MAX_STORIES)
        )
        seen_ids: set = set()
        stories: list = []
        for row in list(trending_result.all()) + list(fresh_result.all()):
            if row[0] in seen_ids:
                continue
            seen_ids.add(row[0])
            stories.append(row)
            if len(stories) >= MAX_STORIES * 2:  # room for both pools
                break

        def _posts_hash(posts: list) -> str:
            # Stable identity of the pool: post ID + text length (+text
            # sha head for cheap text-change detection). Order-independent
            # via sort so a reorder alone doesn't invalidate.
            parts = sorted(
                f"{p.id}:{len(p.text or '')}"
                for p in posts
            )
            return _hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]

        for rank, (story_id, title, post_count) in enumerate(stories, 1):
            try:
                story_obj = await db.get(Story, story_id)

                # Maturity lock: story is old AND has an existing analysis
                # → freeze it and never re-run. Also clears the budget
                # slot for fresher stories.
                if story_obj and story_obj.last_updated_at and isinstance(story_obj.telegram_analysis, dict) and story_obj.telegram_analysis:
                    lu = story_obj.last_updated_at
                    if lu.tzinfo is None:
                        lu = lu.replace(tzinfo=timezone.utc)
                    age_h = (datetime.now(timezone.utc) - lu).total_seconds() / 3600.0
                    if age_h > TELEGRAM_LOCK_HOURS:
                        if not story_obj.telegram_analysis.get("telegram_locked_at"):
                            locked = dict(story_obj.telegram_analysis)
                            locked["telegram_locked_at"] = datetime.now(timezone.utc).isoformat()
                            story_obj.telegram_analysis = locked
                        stats["skipped_locked"] += 1
                        continue

                # Fetch the live pool with the same filters analyze_story_telegram
                # uses so the hash reflects what the analyzer would see.
                pool_q = await db.execute(
                    select(TelegramPost)
                    .where(TelegramPost.story_id == story_id)
                    .where(TelegramPost.text.isnot(None))
                    .where(TelegramPost.text != "")
                )
                pool = list(pool_q.scalars().all())
                cur_hash = _posts_hash(pool) if pool else ""

                if story_obj and isinstance(story_obj.telegram_analysis, dict):
                    prev_hash = story_obj.telegram_analysis.get("posts_hash")
                    if prev_hash and prev_hash == cur_hash:
                        stats["skipped_unchanged"] += 1
                        continue

                # Top-5 use the premium Pass 2 model; the rest drop to
                # baseline. Rank is the trending-ordered position from
                # the SQL above.
                is_premium = rank <= PREMIUM_RANK_LIMIT
                analysis = await analyze_story_telegram(db, str(story_id), is_premium=is_premium)
                if analysis:
                    analysis["posts_hash"] = cur_hash
                    if story_obj:
                        story_obj.telegram_analysis = analysis
                    stats["analyzed"] += 1
                    tier = "premium" if is_premium else "baseline"
                    logger.info(f"Telegram analysis [{tier}] for '{title}': {len(analysis.get('predictions', []))} predictions")
                else:
                    stats["skipped_no_data"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Telegram analysis failed for {story_id}: {e}")

        await db.commit()

    return stats


async def step_telegram_health():
    """Check Telegram session health and channel accessibility."""
    stats = {"session_ok": False, "channels_checked": 0, "channels_failing": []}

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from app.config import settings

        if not settings.telegram_api_id or not settings.telegram_api_hash:
            return {"skipped": True, "reason": "Telegram not configured"}

        session = (
            StringSession(settings.telegram_session_string)
            if settings.telegram_session_string
            else "doornegar_session"
        )
        client = TelegramClient(
            session,
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
    """Three-layer dedup: title match, URL match, embedding similarity.

    Layer 1: Exact title_fa match (existing)
    Layer 2: Same URL (different titles, same article)
    Layer 3: Embedding cosine similarity > 0.92 within 48h (paraphrased reposts)
    """
    from sqlalchemy import select, func
    from datetime import timedelta

    from app.database import async_session
    from app.models.article import Article

    stats = {"title_dupes": 0, "url_dupes": 0, "embedding_dupes": 0, "removed": 0}

    async with async_session() as db:
        # Layer 1: Exact title match
        result = await db.execute(
            select(Article.title_fa, func.count(Article.id))
            .where(
                Article.title_fa.isnot(None),
                func.length(func.trim(Article.title_fa)) >= 10,
            )
            .group_by(Article.title_fa)
            .having(func.count(Article.id) > 1)
            .limit(50)
        )
        for title, count in result.all():
            stats["title_dupes"] += 1
            dupes = await db.execute(
                select(Article).where(Article.title_fa == title).order_by(Article.ingested_at)
            )
            articles = list(dupes.scalars().all())
            if len(articles) <= 1:
                continue
            keeper = articles[0]
            for dupe in articles[1:]:
                if dupe.story_id and dupe.story_id == keeper.story_id:
                    dupe.story_id = None
                    stats["removed"] += 1

        # Layer 2: URL match
        url_result = await db.execute(
            select(Article.url, func.count(Article.id))
            .where(
                Article.url.isnot(None),
                func.length(Article.url) >= 10,
                ~Article.url.like("%t.me/%"),
            )
            .group_by(Article.url)
            .having(func.count(Article.id) > 1)
            .limit(50)
        )
        for url, count in url_result.all():
            stats["url_dupes"] += 1
            dupes = await db.execute(
                select(Article).where(Article.url == url).order_by(Article.ingested_at)
            )
            articles = list(dupes.scalars().all())
            if len(articles) <= 1:
                continue
            keeper = articles[0]
            for dupe in articles[1:]:
                if dupe.story_id and dupe.story_id == keeper.story_id:
                    dupe.story_id = None
                    stats["removed"] += 1

        # Layer 3: Embedding similarity > 0.92 within 48h.
        # D1 — when both an RSS and t.me article from the same outlet
        # land in the same story and look near-identical, prefer the
        # RSS one regardless of length: the canonical URL is the one
        # readers want to follow, and the t.me copy is usually a
        # truncated re-broadcast. Length tiebreaker still applies for
        # RSS-vs-RSS and t.me-vs-t.me cases.
        # Cap raised 200 → 800 so the dedup window covers a busier
        # day's ingest. The O(n²) pairwise check is bounded by
        # `same story_id` so the practical work is n × avg_cluster_size.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        recent = await db.execute(
            select(Article)
            .where(
                Article.ingested_at >= cutoff,
                Article.embedding.isnot(None),
                Article.story_id.isnot(None),
            )
            .order_by(Article.ingested_at.desc())
            .limit(800)
        )
        recent_articles = list(recent.scalars().all())

        def _is_telegram(art) -> bool:
            return bool(art.url) and "t.me/" in art.url

        if len(recent_articles) >= 2:
            from app.nlp.embeddings import cosine_similarity
            seen_ids = set()
            for i, a in enumerate(recent_articles):
                if a.id in seen_ids or not a.embedding:
                    continue
                for b in recent_articles[i + 1:]:
                    if b.id in seen_ids or not b.embedding:
                        continue
                    if a.story_id == b.story_id:
                        sim = cosine_similarity(a.embedding, b.embedding)
                        if sim > 0.92:
                            a_tg = _is_telegram(a)
                            b_tg = _is_telegram(b)
                            if a_tg != b_tg:
                                # One RSS, one Telegram — keep the RSS one.
                                keeper = b if a_tg else a
                            else:
                                # Same kind — fall back to length tiebreak.
                                keeper = a if len(a.content_text or "") >= len(b.content_text or "") else b
                            dupe = b if keeper is a else a
                            dupe.story_id = None
                            seen_ids.add(dupe.id)
                            stats["embedding_dupes"] += 1
                            stats["removed"] += 1

        await db.commit()

    total = stats["title_dupes"] + stats["url_dupes"] + stats["embedding_dupes"]
    if total > 0:
        logger.info(f"Dedup: title={stats['title_dupes']} url={stats['url_dupes']} embed={stats['embedding_dupes']} removed={stats['removed']}")
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


async def step_quality_postprocess():
    """Final quality pass: LLM reviews top 15 stories for article relevance and output quality.

    Sends each story's title, article titles, bias comparison, and side summaries
    to the LLM and asks:
    1. Are all articles relevant to this story? Flag any that don't belong.
    2. Is the bias comparison accurate and fair? Suggest corrections.
    3. Is the title precise enough? Suggest improvement.

    Uses nano model to keep costs low (~$0.005 per story, $0.075 total).
    Only corrects if the LLM finds actual issues — doesn't rewrite for style.
    """
    import json as _json

    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    if not settings.openai_api_key:
        return {"skipped": "no_api_key"}

    QUALITY_PROMPT = """\
شما ویراستار کیفیت سکوی دورنگر هستید. این خبر و مقالات آن را بررسی کنید.

عنوان: {title}
تحلیل سوگیری: {bias}

مقالات:
{articles}

فقط JSON برگردانید:
{{
  "irrelevant_articles": [<شماره مقالاتی که به این خبر ربط ندارند>],
  "bias_correction": "<اگر تحلیل سوگیری اشتباه یا ناقص است، اصلاح پیشنهادی. اگر درست است: null>",
  "title_suggestion": "<اگر عنوان کلی یا نادقیق است، عنوان بهتر. اگر خوب است: null>",
  "quality_score": <عدد 1 تا 5 — کیفیت کلی تحلیل>
}}"""

    stats = {"checked": 0, "articles_flagged": 0, "titles_improved": 0, "bias_corrected": 0}

    async with async_session() as db:
        # Get top 15 visible stories — excluding hand-edited ones. The quality
        # post-process can overwrite title_fa and drop articles, so curated
        # stories must be skipped entirely.
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(
                Story.article_count >= 5,
                Story.summary_fa.isnot(None),
                Story.is_edited.is_(False),
            )
            .order_by(Story.priority.desc(), Story.trending_score.desc())
            .limit(15)
        )
        stories = list(result.scalars().all())

        async def _keepalive(db):
            try:
                await db.execute(text("SELECT 1"))
            except Exception:
                pass

        for story in stories:
            stats["checked"] += 1

            # Build article list
            art_lines = []
            for i, a in enumerate(story.articles[:15], 1):
                art_lines.append(f"{i}. {a.title_fa or a.title_original or '?'}")

            # Get bias from summary_en
            bias = ""
            if story.summary_en:
                try:
                    extras = _json.loads(story.summary_en)
                    bias = extras.get("bias_explanation_fa", "") or ""
                except Exception:
                    pass

            if not bias:
                continue

            prompt = QUALITY_PROMPT.format(
                title=story.title_fa or "",
                bias=bias[:500],
                articles="\n".join(art_lines),
            )

            try:
                await _keepalive(db)
                import openai
                from app.services.llm_helper import build_openai_params
                client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
                params = build_openai_params(
                    model=settings.translation_model,  # nano — cheap
                    prompt=prompt,
                    max_tokens=512,
                    temperature=0,
                )
                response = await client.chat.completions.create(**params)
                from app.services.llm_usage import log_llm_usage
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="quality_postprocess",
                    usage=response.usage,
                    story_id=story.id,
                )
                text_out = response.choices[0].message.content.strip()
                if "```json" in text_out:
                    text_out = text_out.split("```json")[1].split("```")[0].strip()
                elif "```" in text_out:
                    text_out = text_out.split("```")[1].split("```")[0].strip()

                review = _json.loads(text_out)

                # Apply corrections
                irrelevant = review.get("irrelevant_articles", [])
                if irrelevant and isinstance(irrelevant, list):
                    for idx in irrelevant:
                        if isinstance(idx, int) and 1 <= idx <= len(story.articles):
                            article = story.articles[idx - 1]
                            article.story_id = None
                            stats["articles_flagged"] += 1
                            logger.info(f"  QC flagged article #{idx} in '{(story.title_fa or '')[:30]}'")

                title_suggestion = review.get("title_suggestion")
                if title_suggestion and isinstance(title_suggestion, str) and title_suggestion.strip():
                    story.title_fa = title_suggestion.strip()
                    stats["titles_improved"] += 1
                    logger.info(f"  QC improved title: '{title_suggestion[:40]}'")

                # Store quality score
                quality_score = review.get("quality_score")
                if quality_score and story.summary_en:
                    try:
                        extras = _json.loads(story.summary_en)
                        extras["quality_score"] = quality_score
                        story.summary_en = _json.dumps(extras, ensure_ascii=False)
                    except Exception:
                        pass

                await db.commit()

            except Exception as e:
                logger.warning(f"  QC failed for '{(story.title_fa or '')[:30]}': {e}")

    if any(v > 0 for k, v in stats.items() if k != "checked"):
        logger.info(f"Quality postprocess: {stats}")
    return stats


async def step_weekly_digest():
    """Generate a weekly digest (Mondays only). Writes the markdown body
    into a maintenance_logs row with status='weekly_digest' so the
    /weekly-digest endpoint can render it directly. Previously wrote to
    a gitignored on-disk path (`<repo>/project-management/digests/`)
    that didn't exist on Railway, so this step errored every week."""
    from sqlalchemy import select, func, text as _t

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

    week_str = now.strftime("%Y-W%W")
    content = f"""# Weekly Digest — {now.strftime('%B %d, %Y')} ({week_str})

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

    content += """
## System Health
- Auto-maintenance running per the cron schedule
- Check dashboard for detailed metrics: /dashboard

---
*Auto-generated by Doornegar maintenance system*
"""

    # Store the markdown body directly in `results` (Text). The
    # /weekly-digest endpoint reads the most recent row with
    # status='weekly_digest' and returns log.results as the content
    # field, so storing plain markdown matches the reader contract.
    import uuid as _uuid
    async with async_session() as db:
        await db.execute(_t(
            "INSERT INTO maintenance_logs (id, run_at, status, elapsed_s, results) "
            "VALUES (:id, NOW(), 'weekly_digest', 0, :results)"
        ), {"id": _uuid.uuid4(), "results": content})
        await db.commit()

    logger.info(f"Weekly digest written to maintenance_logs (week={week_str})")
    return {"week": week_str, "new_articles": new_articles, "new_stories": new_stories}


async def step_worldview_digests():
    """Weekly worldview synthesis — one card per 4-subgroup bundle.

    Monday-only. For each bundle (principlist, reformist, moderate_diaspora,
    radical_diaspora), aggregates the past 7 days of articles + bias
    analyses into a compact frequency table, then calls Claude once to
    synthesize a worldview card describing what those OUTLETS told their
    readers (not what readers believe). Bundles that fail preconditions
    (<3 sources, <20 articles, <75% bias coverage) get status='insufficient'
    rows so the UI can render a "not enough signal" placeholder instead
    of hiding them.
    """
    now = datetime.now()
    if now.weekday() != 0:
        return {"skipped": True, "reason": "Not Monday"}

    from app.database import async_session
    from app.services.worldview_digest import generate_worldview_digests

    async with async_session() as db:
        stats = await generate_worldview_digests(db)

    logger.info(
        f"Worldview digests: {len(stats.get('per_bundle', {}))} bundles processed, "
        f"total cost ${stats.get('total_cost_usd', 0):.4f}"
    )
    return stats


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


async def step_flag_unrelated_articles():
    """Auto-detach articles whose embedding is far from their story's centroid.

    Computes cosine similarity between each article's embedding and its
    story's centroid_embedding. Articles below the threshold are
    **detached from the story** (story_id set to NULL) so the next
    clustering run re-places them. No human-review queue involved —
    the dashboard's improvement list is for rater-submitted feedback only.

    Legacy bot entries (device_info='maintenance-bot') in
    ImprovementFeedback are deleted on every run so stale auto-flags
    don't accumulate.
    """
    from sqlalchemy import delete, select, update
    from app.database import async_session
    from app.models.article import Article
    from app.models.improvement import ImprovementFeedback
    from app.models.story import Story
    from app.nlp.embeddings import cosine_similarity

    THRESHOLD = 0.25                  # below this = almost-certainly misclustered
    MAX_DETACH_PER_RUN = 50           # soft cap — prevents a bad centroid from emptying a whole story

    stats = {"checked": 0, "detached": 0, "legacy_cleaned": 0, "skipped_no_centroid": 0}

    async with async_session() as db:
        # One-time / idempotent cleanup: remove the obsolete bot-flagged
        # improvement entries. They predate this auto-detach logic and
        # clutter the admin todo list.
        cleanup = await db.execute(
            delete(ImprovementFeedback).where(
                ImprovementFeedback.device_info == "maintenance-bot",
            )
        )
        stats["legacy_cleaned"] = cleanup.rowcount or 0

        # Get visible stories with centroids
        result = await db.execute(
            select(Story).where(
                Story.article_count >= 5,
                Story.centroid_embedding.isnot(None),
            )
        )
        stories = list(result.scalars().all())

        detached_ids: list = []
        for story in stories:
            if len(detached_ids) >= MAX_DETACH_PER_RUN:
                break
            centroid = story.centroid_embedding
            if not centroid:
                stats["skipped_no_centroid"] += 1
                continue

            art_result = await db.execute(
                select(Article).where(
                    Article.story_id == story.id,
                    Article.embedding.isnot(None),
                )
            )
            articles = list(art_result.scalars().all())

            for article in articles:
                stats["checked"] += 1
                if not article.embedding:
                    continue
                sim = cosine_similarity(article.embedding, centroid)
                if sim < THRESHOLD:
                    detached_ids.append(article.id)
                    logger.info(
                        "  Detaching article %s (sim=%.2f) from story '%s' — will be re-clustered on next run",
                        str(article.id)[:8],
                        sim,
                        (story.title_fa or "")[:30],
                    )
                    if len(detached_ids) >= MAX_DETACH_PER_RUN:
                        break

        if detached_ids:
            await db.execute(
                update(Article)
                .where(Article.id.in_(detached_ids))
                .values(story_id=None)
            )
            stats["detached"] = len(detached_ids)

        await db.commit()

    if stats["detached"] > 0:
        logger.info(f"Auto-flag: {stats}")
    return stats


async def step_image_relevance():
    """Check if story images match their titles and swap if a better one exists.

    For each visible story, compare the current best image (from _story_brief_with_extras)
    against the story title using word overlap. If an article has a much better
    title match, mark the current image as low-relevance in the dashboard.
    Also: for stories where the image comes from a different topic, flag it.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    stats = {"checked": 0, "swapped": 0, "flagged": 0}

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(Story.article_count >= 5)
            .limit(100)
        )
        stories = list(result.scalars().all())

        for story in stories:
            stats["checked"] += 1
            story_words = {w for w in (story.title_fa or "").split() if len(w) >= 3}
            if not story_words:
                continue

            # Find articles with images
            candidates = [
                a for a in story.articles
                if a.image_url and len(a.image_url) > 10
                and "localhost" not in a.image_url
                and "pixel" not in a.image_url.lower()
            ]
            if not candidates:
                continue

            # Score each by title word overlap
            best_score = -1
            best_article = None
            for a in candidates:
                art_words = {w for w in (a.title_fa or a.title_original or "").split() if len(w) >= 3}
                overlap = len(story_words & art_words)
                # Prefer R2/stable URLs
                from app.config import settings
                is_stable = a.image_url.startswith("/images/") or (
                    settings.r2_public_url and a.image_url.startswith(settings.r2_public_url)
                )
                score = overlap * 2 + (1 if is_stable else 0)
                if score > best_score:
                    best_score = score
                    best_article = a

            # If best image has 0 word overlap with story title, flag it
            if best_article and best_score <= 1:
                stats["flagged"] += 1
                logger.info(f"  Low relevance image for '{(story.title_fa or '')[:30]}' — best overlap score: {best_score}")

    if stats["flagged"] > 0:
        logger.info(f"Image relevance: {stats}")
    return stats


async def step_detect_silences():
    """Detect one-sided coverage silences in visible stories.

    For each visible story (article_count >= 5):
    1. Check which source alignments covered it
    2. If 3+ articles from one side and 0 from the other -> silence
    3. Store silence record in story's summary_en JSON
    4. For top 5 most significant silences, use LLM to generate a hypothesis
    """
    import json as _json

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    stats = {"checked": 0, "silences_found": 0, "hypotheses_generated": 0, "failed": 0}

    # Partition by the 4-subgroup narrative taxonomy, collapsed to 2 sides:
    # inside-border (principlist + reformist) vs outside-border
    # (moderate_diaspora + radical_diaspora). Etemad-Online and any future
    # inside-reformist source correctly count toward inside-border here,
    # whereas the old state_alignment-based partition put it in diaspora.
    from app.services.narrative_groups import narrative_group as _ng_silence, side_of as _side_of
    INSIDE = "inside"
    OUTSIDE = "outside"

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 5)
            .order_by(Story.trending_score.desc())
            .limit(200)
        )
        stories = list(result.scalars().all())

        silences: list[tuple[Story, str, int, dict]] = []  # (story, silent_side, loud_count, existing_extra)

        for story in stories:
            stats["checked"] += 1

            # Count articles per side (inside vs outside)
            state_count = 0   # variable name retained for minimal blast radius downstream
            diaspora_count = 0
            state_sources: list[str] = []
            diaspora_sources: list[str] = []

            for a in story.articles:
                if not a.source:
                    continue
                side = _side_of(_ng_silence(a.source))
                if side == INSIDE:
                    state_count += 1
                    slug = a.source.slug
                    if slug not in state_sources:
                        state_sources.append(slug)
                elif side == OUTSIDE:
                    diaspora_count += 1
                    slug = a.source.slug
                    if slug not in diaspora_sources:
                        diaspora_sources.append(slug)

            # Parse existing summary_en JSON
            extra = {}
            if story.summary_en:
                try:
                    extra = _json.loads(story.summary_en)
                except Exception:
                    pass

            # Check for silence: 3+ from one side, 0 from the other
            silent_side = None
            loud_count = 0
            if state_count >= 3 and diaspora_count == 0:
                silent_side = "diaspora"
                loud_count = state_count
            elif diaspora_count >= 3 and state_count == 0:
                silent_side = "state"
                loud_count = diaspora_count

            if silent_side:
                stats["silences_found"] += 1
                silence_record = {
                    "silent_side": silent_side,
                    "loud_side": "state" if silent_side == "diaspora" else "diaspora",
                    "loud_count": loud_count,
                    "loud_sources": state_sources if silent_side == "diaspora" else diaspora_sources,
                }
                extra["silence_analysis"] = silence_record
                story.summary_en = _json.dumps(extra, ensure_ascii=False)
                silences.append((story, silent_side, loud_count, extra))
            elif "silence_analysis" in extra:
                # Clear stale silence if story now has coverage from both sides
                del extra["silence_analysis"]
                story.summary_en = _json.dumps(extra, ensure_ascii=False)

        # Sort silences by significance (loud_count * trending_score)
        silences.sort(
            key=lambda x: x[2] * (x[0].trending_score or 0),
            reverse=True,
        )

        # Generate LLM hypotheses for top 5 silences only
        top_silences = silences[:5]
        if top_silences and settings.openai_api_key:
            from openai import OpenAI
            from app.services.llm_helper import build_openai_params

            client = OpenAI(api_key=settings.openai_api_key)

            for story, silent_side, loud_count, extra in top_silences:
                side_label = "دولتی" if silent_side == "state" else "اپوزیسیون/مستقل"
                title = story.title_fa or story.title_en or "(بدون عنوان)"

                try:
                    params = build_openai_params(
                        model=settings.translation_model,  # nano — cheap
                        prompt=(
                            f"این خبر فقط توسط رسانه‌های {'دولتی' if silent_side == 'diaspora' else 'اپوزیسیون'} پوشش داده شده و "
                            f"رسانه‌های {side_label} آن را نادیده گرفته‌اند.\n\n"
                            f"عنوان خبر: {title}\n\n"
                            f"یک جمله فارسی بنویس که فرضیه‌ای درباره دلیل این سکوت ارائه دهد. "
                            f"فقط یک جمله، بدون توضیح اضافی."
                        ),
                        max_tokens=200,
                        temperature=0.3,
                    )
                    resp = client.chat.completions.create(**params)
                    from app.services.llm_usage import log_llm_usage
                    await log_llm_usage(
                        model=settings.translation_model,
                        purpose="detect_silences",
                        usage=resp.usage,
                        story_id=story.id,
                    )
                    hypothesis = resp.choices[0].message.content.strip()

                    extra["silence_analysis"]["hypothesis_fa"] = hypothesis
                    story.summary_en = _json.dumps(extra, ensure_ascii=False)
                    stats["hypotheses_generated"] += 1
                    logger.info(f"  Silence: {side_label} silent on '{title[:40]}' — hypothesis generated")
                except Exception as e:
                    logger.warning(f"  Silence hypothesis failed for '{(story.title_fa or '')[:30]}': {e}")
                    stats["failed"] += 1

        await db.commit()

    if stats["silences_found"] > 0:
        logger.info(
            f"Silence detection: {stats['silences_found']} silences found, "
            f"{stats['hypotheses_generated']} hypotheses generated"
        )
    return stats


async def step_detect_coordination():
    """Detect coordinated messaging within alignment groups.

    1. Get all articles from the last 24 hours
    2. Group by source alignment
    3. Within each group, compute pairwise cosine similarity
    4. If 3+ articles from different sources have cosine > 0.85
       AND were published within 6 hours of each other -> flag as coordinated
    5. Store in story's summary_en JSON under "coordinated_messaging"
    """
    import json as _json

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.nlp.embeddings import cosine_similarity

    stats = {"checked": 0, "coordination_detected": 0, "stories_flagged": 0}

    async with async_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Get recent articles with embeddings and sources
        result = await db.execute(
            select(Article)
            .options(selectinload(Article.source))
            .where(
                Article.published_at >= cutoff,
                Article.embedding.isnot(None),
                Article.source_id.isnot(None),
                Article.story_id.isnot(None),
            )
            .order_by(Article.published_at.desc())
            .limit(500)
        )
        articles = list(result.scalars().all())
        stats["checked"] = len(articles)

        if len(articles) < 3:
            return stats

        # Group by source alignment
        by_alignment: dict[str, list[Article]] = {}
        for a in articles:
            if not a.source:
                continue
            align = a.source.state_alignment or "unknown"
            by_alignment.setdefault(align, []).append(a)

        # Within each alignment group, find coordinated clusters
        coordination_by_story: dict[str, dict] = {}  # story_id -> coordination record

        for align, group_articles in by_alignment.items():
            if len(group_articles) < 3:
                continue

            # Cap group size to avoid O(n^2) explosion
            if len(group_articles) > 50:
                group_articles = group_articles[:50]

            # Build pairwise similarity for qualifying pairs
            pairs_cache: dict[tuple, float] = {}
            for i, a in enumerate(group_articles):
                for j in range(i + 1, len(group_articles)):
                    b = group_articles[j]
                    # Only compare articles from DIFFERENT sources
                    if a.source_id == b.source_id:
                        continue
                    if not a.embedding or not b.embedding:
                        continue
                    sim = cosine_similarity(a.embedding, b.embedding)
                    if sim > 0.85:
                        # Check time window: within 6 hours
                        if a.published_at and b.published_at:
                            time_diff = abs((a.published_at - b.published_at).total_seconds()) / 3600
                            if time_diff <= 6:
                                pairs_cache[(i, j)] = sim

            if not pairs_cache:
                continue

            # Build adjacency from qualifying pairs
            adj: dict[int, set[int]] = {}
            for (i, j) in pairs_cache:
                adj.setdefault(i, set()).add(j)
                adj.setdefault(j, set()).add(i)

            # Find connected components (BFS)
            visited: set[int] = set()
            clusters: list[list[int]] = []
            for node in adj:
                if node in visited:
                    continue
                component = []
                queue = [node]
                while queue:
                    curr = queue.pop(0)
                    if curr in visited:
                        continue
                    visited.add(curr)
                    component.append(curr)
                    for neighbor in adj.get(curr, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                if len(component) >= 3:
                    clusters.append(component)

            for cluster_indices in clusters:
                cluster_articles = [group_articles[i] for i in cluster_indices]

                # Ensure at least 3 different sources
                unique_sources = {a.source.slug for a in cluster_articles if a.source}
                if len(unique_sources) < 3:
                    continue

                stats["coordination_detected"] += 1

                # Compute average similarity across the cluster
                sim_values = []
                for (i, j), sim in pairs_cache.items():
                    if i in cluster_indices and j in cluster_indices:
                        sim_values.append(sim)
                avg_sim = sum(sim_values) / len(sim_values) if sim_values else 0

                # Compute time window
                pub_times = [a.published_at for a in cluster_articles if a.published_at]
                if pub_times:
                    time_window = (max(pub_times) - min(pub_times)).total_seconds() / 3600
                else:
                    time_window = 0

                # Group by story_id and store
                for a in cluster_articles:
                    sid = str(a.story_id)
                    if sid not in coordination_by_story:
                        coordination_by_story[sid] = {
                            "side": align,
                            "sources": list(unique_sources),
                            "similarity": round(avg_sim, 2),
                            "time_window_hours": round(time_window, 1),
                        }

        # Write coordination records into story summary_en JSON
        if coordination_by_story:
            import uuid as _uuid
            story_ids = []
            for sid in coordination_by_story:
                try:
                    story_ids.append(_uuid.UUID(sid))
                except (ValueError, AttributeError):
                    continue

            if story_ids:
                story_result = await db.execute(
                    select(Story).where(Story.id.in_(story_ids))
                )
                for story in story_result.scalars().all():
                    extra = {}
                    if story.summary_en:
                        try:
                            extra = _json.loads(story.summary_en)
                        except Exception:
                            pass

                    coord = coordination_by_story.get(str(story.id))
                    if coord:
                        extra["coordinated_messaging"] = coord
                        story.summary_en = _json.dumps(extra, ensure_ascii=False)
                        stats["stories_flagged"] += 1

                await db.commit()

    if stats["coordination_detected"] > 0:
        logger.info(
            f"Coordination detection: {stats['coordination_detected']} clusters found, "
            f"{stats['stories_flagged']} stories flagged"
        )
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
                    from app.services.llm_usage import log_llm_usage
                    await log_llm_usage(
                        model=settings.translation_model,
                        purpose="fix_issues.translate",
                        usage=resp.usage,
                        meta={"batch_size": len(batch)},
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


async def step_snapshot_analyses():
    """Capture the analysis axes of every visible story into
    `stories.analysis_snapshot_24h` for next-day comparison.

    Runs near the end of nightly maintenance so the snapshot reflects
    the latest re-analysis, merges, and hand edits. The next day's
    homepage render compares live state to this snapshot and decides
    whether the story has a "significant update" worth repeating in
    the hero slot (or surfacing as a بروزرسانی badge).

    Idempotent: running it again in the same nightly window just
    overwrites with identical values. The column is also self-creating
    via `ALTER TABLE IF NOT EXISTS` — same idiom as editorial_context_fa
    so new deploys don't need a separate migration step.
    """
    import json as _json

    from sqlalchemy import select, text

    from app.database import async_session
    from app.models.story import Story
    from app.services.story_freshness import build_snapshot
    from app.services.narrative_groups import counts_to_percentages, narrative_group

    stats = {"snapshotted": 0, "skipped": 0, "failed": 0}

    async with async_session() as db:
        # Self-creating column — matches the step_editorial pattern.
        await db.execute(text(
            "ALTER TABLE stories ADD COLUMN IF NOT EXISTS analysis_snapshot_24h JSONB"
        ))
        await db.commit()

    async with async_session() as db:
        # Eager-load both articles AND their sources. The pct calculation
        # below reads `a.source.production_location` / factional_alignment
        # / state_alignment, and in async SQLAlchemy a lazy-loaded
        # relationship access blows up with MissingGreenlet — which the
        # except block below silently caught, zeroing every snapshot
        # (and later making every story falsely flag "پوشش ... آغاز شد"
        # on the homepage).
        from sqlalchemy.orm import selectinload
        from app.models.article import Article
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
        )
        stories = list(result.scalars().all())

        for story in stories:
            try:
                blob = _json.loads(story.summary_en) if story.summary_en else {}
            except Exception:
                blob = {}

            # Derive inside/outside border pct from the narrative-group
            # counts of the story's articles. Wrapped so a single bad
            # source row doesn't zero the whole snapshot.
            try:
                counts: dict[str, int] = {}
                for a in story.articles or []:
                    grp = narrative_group(a.source) if a.source else None
                    if grp:
                        counts[grp] = counts.get(grp, 0) + 1
                pct = counts_to_percentages(counts)
                inside_pct = (pct.get("principlist", 0) or 0) + (pct.get("reformist", 0) or 0)
                outside_pct = (pct.get("moderate_diaspora", 0) or 0) + (pct.get("radical_diaspora", 0) or 0)
            except Exception as _e:
                logger.warning(f"snapshot pct calc failed for {story.id}: {_e}")
                inside_pct = 0
                outside_pct = 0

            snapshot = build_snapshot(
                article_count=story.article_count,
                dispute_score=blob.get("dispute_score"),
                inside_pct=inside_pct,
                outside_pct=outside_pct,
                bias_explanation_fa=blob.get("bias_explanation_fa"),
                # state_summary_fa and diaspora_summary_fa live inside the
                # same summary_en JSONB blob as bias_explanation_fa, not as
                # direct Story columns.
                state_summary_fa=blob.get("state_summary_fa"),
                diaspora_summary_fa=blob.get("diaspora_summary_fa"),
            )
            story.analysis_snapshot_24h = snapshot
            stats["snapshotted"] += 1

        await db.commit()

    logger.info(f"Snapshot analyses: {stats}")
    return stats


async def step_audit_cluster_coherence():
    """Phase 3 of the clustering upgrade. For every cluster of ≥10
    articles, sample a handful and check pairwise cosine similarity.
    Flag stories where any sampled pair is below threshold — those
    are candidates for Niloofar to split / prune / rename.

    No LLM, no edits to bias or summaries — just writes
    stories.audit_notes.cluster_drift with evidence. Niloofar surfaces
    the flagged ones in the next audit.
    """
    from app.database import async_session
    from app.services.clustering import audit_cluster_coherence

    async with async_session() as db:
        stats = await audit_cluster_coherence(db)
    logger.info(f"Cluster coherence audit: {stats}")
    return stats


async def step_editorial():
    """Generate editorial context for top 30 trending stories.

    Writes 2-3 sentences of background context ('what you need to know')
    per story into story.editorial_context_fa using the nano model.

    A Claude-driven Niloofar audit can override these blurbs via the
    update_editorial fix type — this step is the cheap default that keeps
    coverage broad until an audit improves a specific story.

    Previously ran on top 15. Expanded to 30 so the "what you need to know"
    blurb appears on a larger slice of the homepage.
    """
    from sqlalchemy import select, text, update
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    stats = {"generated": 0, "skipped": 0, "failed": 0}

    # Ensure column exists
    async with async_session() as db:
        await db.execute(text(
            "ALTER TABLE stories ADD COLUMN IF NOT EXISTS editorial_context_fa JSONB"
        ))
        await db.commit()

    # Fetch top trending stories
    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(30)
        )
        stories = list(result.scalars().all())

    if not stories:
        logger.info("Editorial: no stories found")
        return stats

    import openai
    from app.services.llm_helper import build_openai_params

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    editorial_prompt = """تو سردبیر ارشد با ۲۰ سال تجربه در ژئوپلیتیک خاورمیانه هستی.

وظیفه تو نوشتن «زمینه خبر» (آنچه باید بدانید) برای یک موضوع خبری است.
این متن به خواننده کمک می‌کند بفهمد چرا این خبر مهم است و پیشینه آن چیست.

عنوان: {title_fa}
خلاصه: {summary_fa}
تعداد مقالات: {article_count} | منابع: {source_count}

عناوین مقالات:
{article_titles}

دستورالعمل:
- دقیقا ۲ تا ۳ جمله بنویس
- زمینه تاریخی یا سیاسی مرتبط را توضیح بده
- بدون تکرار عنوان یا خلاصه
- بدون قضاوت — فقط واقعیت‌ها
- فقط متن ساده برگردان"""

    for story in stories:
        # Skip if already has fresh context (generated in last 12 hours)
        if story.editorial_context_fa:
            existing = story.editorial_context_fa
            if isinstance(existing, dict) and existing.get("generated_at"):
                try:
                    gen_time = datetime.fromisoformat(existing["generated_at"])
                    if (datetime.now(timezone.utc) - gen_time).total_seconds() < 43200:
                        stats["skipped"] += 1
                        continue
                except (ValueError, TypeError):
                    pass

        # Build article titles list
        titles = []
        for a in story.articles[:8]:
            t = a.title_fa or a.title_original or "?"
            src = a.source.name_fa if a.source else "?"
            titles.append(f"- [{src}] {t[:80]}")

        prompt = editorial_prompt.format(
            title_fa=story.title_fa or "",
            summary_fa=(story.summary_fa or "")[:300],
            article_count=story.article_count,
            source_count=story.source_count,
            article_titles="\n".join(titles),
        )

        params = build_openai_params(
            model=settings.translation_model,  # gpt-4.1-nano
            prompt=prompt,
            max_tokens=512,
            temperature=0.3,
        )

        try:
            response = await client.chat.completions.create(**params)
            from app.services.llm_usage import log_llm_usage
            await log_llm_usage(
                model=settings.translation_model,
                purpose="editorial",
                usage=response.usage,
                story_id=story.id,
            )
            context_text = response.choices[0].message.content.strip()
            context_data = {
                "context": context_text,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": settings.translation_model,
            }

            async with async_session() as db:
                await db.execute(
                    update(Story)
                    .where(Story.id == story.id)
                    .values(editorial_context_fa=context_data)
                )
                await db.commit()
            stats["generated"] += 1
            logger.info(f"Niloofar editorial: generated for '{story.title_fa[:40]}'")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"Niloofar editorial failed for story {story.id}: {e}")

    logger.info(f"Niloofar editorial: {stats}")
    return stats


async def step_niloofar_polish_telegram():
    """Niloofar polishes Telegram predictions + claims for homepage display.

    Pass-2 of the Telegram analysis is asked to prefix each claim with
    "موضوع: <topic> | ..." so competing claims about the same subject group
    together. That's useful on the story detail page, but on the homepage
    hero strip the label prefix buries the actual content. Predictions
    often leak an "در آینده،" prefix too, which is redundant once the
    section is already titled "پیش‌بینی‌ها".

    Niloofar rewrites each item:
      - Drops label prefixes ("موضوع: X |", "تعداد تلفات: N |", etc.)
      - Drops "در آینده،" from predictions (the section implies future)
      - Keeps channel attribution and credibility cue ("مشکوک",
        "معتبر", "نیازمند تأیید")
      - Tightens wording to one punchy sentence

    Results go in story.telegram_analysis.predictions_display and
    key_claims_display. Raw fields stay untouched so the detail page's
    topic-grouping still works.
    """
    import json as _json
    from sqlalchemy import select, update
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.database import async_session
    from app.models.story import Story

    stats = {"polished": 0, "skipped": 0, "failed": 0, "no_analysis": 0}

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .where(Story.article_count >= 2)
            .order_by(Story.trending_score.desc())
            .limit(30)
        )
        stories = list(result.scalars().all())

    if not stories:
        logger.info("Niloofar polish telegram: no stories found")
        return stats

    import openai
    from app.services.llm_helper import build_openai_params

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    polish_prompt = """تو نیلوفر هستی، سردبیر ارشد خبری.

وظیفه: تمیزکاری ادعاها و پیش‌بینی‌های تلگرامی برای نمایش به خواننده. متن اصلی توسط مدل دیگری تولید شده و شامل برچسب‌ها، نام کانال‌ها و نقل‌قول‌های اضافی است که باید حذف شوند. خواننده فقط جوهرِ پیش‌بینی یا ادعا را می‌خواهد — نه نامِ کانال، نه نقل‌قول.

═══ تعریف‌ها ═══
- **پیش‌بینی**: گزاره‌ای دربارهٔ اتفاقِ آینده. فعلِ آینده‌دار دارد (خواهد، می‌شود، رخ می‌دهد).
- **ادعا**: اطلاعاتی که یک طرف مدعی دانستنِ آن است و دیگران نمی‌دانند یا انکار می‌کنند. دربارهٔ گذشته یا حالِ واقعی — نه آینده.
- اگر آیتمی در predictions فعلِ آینده ندارد، در واقع ادعاست — خالی برگردان.
- اگر آیتمی در key_claims فعلِ آینده دارد، در واقع پیش‌بینی است — خالی برگردان.

═══ قواعد مشترک ═══
- **نام کانال در متن ممنوع**. «کانال مصاف»، «کانال آخرین خبر»، «وحید آنلاین» — همه حذف. اگر نیاز بود بیاورش در انتهای جمله در پرانتز.
- **نقل‌قول مستقیم ممنوع**. «گفت که …»، «نوشت …»، «اعلام کرد …» — همه حذف. فقط جوهر ادعا یا پیش‌بینی، مستقیم.
- بدون افزودن معنای جدید — فقط تمیز کن.
- خروجی فقط JSON.

═══ قواعد پیش‌بینی‌ها ═══
- حذف پیشوند «در آینده،» (عنوان بخش خودش «پیش‌بینی‌ها» است).
- حذف «احتمالاً»، «به احتمال زیاد»، «شاید»، «ممکن است» در ابتدا.
- اگر قطعیت درصدی آمده («۷۰ درصد احتمال دارد»)، حفظش کن.
- **پیش‌بینیِ فرا-رسانه‌ای ممنوع**: «کانال‌های اپوزیسیون تأکید خواهند کرد» → حذف (خالی برگردان). پیش‌بینی دربارهٔ خودِ رویداد باشد، نه دربارهٔ پوششِ رسانه‌ای.

═══ قواعد ادعاها ═══
- **حذف پیشوندهای برچسبی** در صدر: «موضوع: … |»، «تعداد تلفات: N |»، «ادعا:»، «ادعا: «…»»، «پوشش: …». اگر ادعا داخل «…» یا "…" پیچیده شده، گیومه‌ها را حذف کن و فقط متنِ داخل را نگه دار.
- **حذف انتسابِ کانال در هر موقعیت**: «— کانال X»، «— کانال X نقل قول از Y»، «— کانال X ارجاع به Y»، «— کانال‌های …». این دنباله‌ها باید کاملاً حذف شوند، چه در میانه چه در انتها.
- **حذف دنبالهٔ «— ارزیابی: …»**. متنِ ارزیابی فقط برای استخراج برچسب اعتبار استفاده می‌شود (به‌صورت یک کلمه‌کلیدی)، نه نمایش به خواننده. واژگان رایج و برچسبِ متناظرشان:
    * «قابل‌اعتماد»، «معتبر»، «موثق»، «قابل‌استناد»، «تأیید شده»، «چند منبع تأیید کرده» → برچسب «تأیید شده»
    * «مشکوک»، «اغراق»، «بعید»، «منابع متناقض»، «منابع مستقل تأیید نکرده‌اند» → «مشکوک»
    * «تبلیغاتی»، «جانبدار»، «پروپاگاند»، «جنبه تبلیغی» → «تبلیغاتی»
    * «تک‌منبع»، «فقط یک کانال»، «تکرار نشده» → «تک‌منبع»
    * «نیازمند تأیید»، «هنوز منابع مستقل وارد نشده» → «نیازمند تأیید»
- برچسب اعتبار در صدر، سپس دونقطه، سپس ادعا. برچسب‌های مجاز:
    * «تأیید شده:» — چند منبع مستقل تأیید کرده‌اند
    * «مشکوک:» — منبع مستقل تأیید نکرده یا ارقام متناقض‌اند
    * «تبلیغاتی:» — لحن و واژگان آشکارا تبلیغاتی‌اند
    * «تک‌منبع:» — فقط یک کانال ادعا کرده و تکرار یا تأیید نشده
    * «نیازمند تأیید:» — در مرحلهٔ ابهام، هنوز منابع مستقل وارد نشده‌اند
- اگر برچسب از متن قابل تشخیص نیست، بدون برچسب بنویس.

═══ نمونه‌های قبل / بعد ═══

پیش‌بینی قبل: «احتمالاً در هفته‌های آینده مذاکرات مجدد رخ خواهد داد.»
پیش‌بینی بعد: «در هفته‌های آینده مذاکرات مجدد رخ خواهد داد.»

پیش‌بینی قبل: «کانال‌های اپوزیسیون روی شکست مذاکرات تأکید خواهند کرد.»
پیش‌بینی بعد: «» (حذف — فرا-رسانه‌ای)

پیش‌بینی قبل: «کانال وحید آنلاین پیش‌بینی کرد که ونس به تهران سفر خواهد کرد.»
پیش‌بینی بعد: «ونس به تهران سفر خواهد کرد.»

ادعا قبل: «موضوع: نتیجه مذاکرات | کانال آخرین خبر ادعا کرد مذاکرات پس از ۲۱ ساعت به بن‌بست رسید — معتبر.»
ادعا بعد: «تأیید شده: مذاکرات پس از ۲۱ ساعت به بن‌بست رسید.»

ادعا قبل: «کانال‌های حکومتی اعلام کردند نیروهای آمریکا در عراق شکست سنگین خورده‌اند.»
ادعا بعد: «تبلیغاتی: نیروهای آمریکا در عراق شکست سنگین خورده‌اند.»

ادعا قبل: «کانال مصاف گفت ۵۰۰ موشک در حملهٔ دیشب شلیک شده — مشکوک، منابع مستقل رقم کمتری می‌دهند.»
ادعا بعد: «مشکوک: ۵۰۰ موشک در حملهٔ دیشب شلیک شده.»

ادعا قبل (اما در واقع پیش‌بینی): «کانال X می‌گوید آتش‌بس تا پایان ماه خواهد شکست.»
ادعا بعد: «» (حذف — فعل آینده دارد، باید پیش‌بینی می‌بود)

ادعا قبل: «ادعا: «آمریکا و ایران خواهان بازگشت به جنگ نیستند، اما اعتمادی وجود ندارد» — کانال ML Strategy ارجاع به مارکو ویچنتینو — ارزیابی: تحلیل میانه‌رو و قابل‌استناد به‌عنوان ارزیابی مبتنی بر ملاحظات استراتژیک، اما فاقد شواهد عددی دقیق.»
ادعا بعد: «تأیید شده: آمریکا و ایران خواهان بازگشت به جنگ نیستند، اما اعتمادی وجود ندارد.»

ادعا قبل: «ادعا: «ترامپ با اعمال محاصره و نقض آتش‌بس می‌خواهد میز مذاکره را به میز تسلیم تبدیل کند» — کانال ML Strategy — ارزیابی: تفسیر سیاسی از نیت آمریکا؛ منطقی اما اظهارنظر تحلیلی و تا حدی جانبدار.»
ادعا بعد: «تبلیغاتی: ترامپ با اعمال محاصره و نقض آتش‌بس می‌خواهد میز مذاکره را به میز تسلیم تبدیل کند.»

ادعا قبل: «ادعا: «ما مذاکره زیر سایه تهدید را نمی‌پذیریم» — کانال farahmand_alipour نقل قول از نابویان — ارزیابی: قابل‌اعتماد برای بازتاب موضع رسمی (جانبدارانه اما موثق).»
ادعا بعد: «تأیید شده: ما مذاکره زیر سایه تهدید را نمی‌پذیریم.»

═══ ورودی ═══
عنوان موضوع: {title_fa}

پیش‌بینی‌های خام:
{predictions_json}

ادعاهای خام:
{claims_json}

═══ خروجی ═══
JSON با این ساختار:
{{
  "predictions": ["متن تمیز شده ۱", "متن تمیز شده ۲", ...],
  "key_claims": ["متن تمیز شده ۱", "متن تمیز شده ۲", ...]
}}

تعداد آیتم‌های خروجی باید دقیقاً با تعداد ورودی برابر باشد، به همان ترتیب."""

    for story in stories:
        analysis = story.telegram_analysis
        if not analysis or not isinstance(analysis, dict):
            stats["no_analysis"] += 1
            continue

        raw_preds = analysis.get("predictions") or []
        raw_claims = analysis.get("key_claims") or []

        if not raw_preds and not raw_claims:
            stats["no_analysis"] += 1
            continue

        # Skip if already polished against these exact raw items. We hash
        # the raw texts so a new Pass-2 result triggers a re-polish.
        def _digest(items):
            texts = [i if isinstance(i, str) else (i.get("text") or "") for i in items]
            return "|".join(t[:40] for t in texts)

        raw_digest = _digest(raw_preds) + "::" + _digest(raw_claims)
        if analysis.get("display_digest") == raw_digest and analysis.get("predictions_display") is not None:
            stats["skipped"] += 1
            continue

        # Extract plain text for the LLM; keep metadata (pct, supporters) to
        # merge back after polish.
        def _text_of(it):
            return it if isinstance(it, str) else (it.get("text") or "")

        pred_texts = [_text_of(p) for p in raw_preds]
        claim_texts = [_text_of(c) for c in raw_claims]

        prompt = polish_prompt.format(
            title_fa=story.title_fa or "",
            predictions_json=_json.dumps(pred_texts, ensure_ascii=False),
            claims_json=_json.dumps(claim_texts, ensure_ascii=False),
        )

        params = build_openai_params(
            model=settings.translation_model,  # gpt-4.1-nano — cheap
            prompt=prompt,
            max_tokens=1500,
            temperature=0.2,
        )
        # Force JSON output
        params["response_format"] = {"type": "json_object"}

        try:
            response = await client.chat.completions.create(**params)
            from app.services.llm_usage import log_llm_usage
            await log_llm_usage(
                model=settings.translation_model,
                purpose="niloofar.polish_telegram",
                usage=response.usage,
                story_id=story.id,
            )
            content = response.choices[0].message.content.strip()
            parsed = _json.loads(content)
            polished_preds = parsed.get("predictions") or []
            polished_claims = parsed.get("key_claims") or []

            # If the model returned the wrong count, skip rather than mix
            # polished and raw items in unpredictable ways.
            if len(polished_preds) != len(pred_texts) or len(polished_claims) != len(claim_texts):
                stats["failed"] += 1
                logger.warning(
                    f"Niloofar polish: count mismatch for {story.id} "
                    f"({len(polished_preds)}/{len(pred_texts)}, {len(polished_claims)}/{len(claim_texts)})"
                )
                continue

            # Merge polished text back into original shape (object with
            # pct/supporters/text, or plain string).
            def _merge(raw, polished_text):
                if isinstance(raw, str):
                    return polished_text
                merged = dict(raw)
                merged["text"] = polished_text
                return merged

            # Drop items Niloofar polished to empty — that's her signal
            # for "this was a meta-prediction / pure commentary with no real
            # content, don't show it". An empty string would render as a
            # blank row on the homepage; keeping it out of the display list
            # is cleaner.
            predictions_display = [
                _merge(raw_preds[i], polished_preds[i])
                for i in range(len(raw_preds))
                if (polished_preds[i] or "").strip()
            ]
            key_claims_display = [
                _merge(raw_claims[i], polished_claims[i])
                for i in range(len(raw_claims))
                if (polished_claims[i] or "").strip()
            ]

            new_analysis = dict(analysis)
            new_analysis["predictions_display"] = predictions_display
            new_analysis["key_claims_display"] = key_claims_display
            new_analysis["display_digest"] = raw_digest
            new_analysis["display_generated_at"] = datetime.now(timezone.utc).isoformat()

            async with async_session() as db:
                await db.execute(
                    update(Story)
                    .where(Story.id == story.id)
                    .values(telegram_analysis=new_analysis)
                )
                await db.commit()
            stats["polished"] += 1
            logger.info(f"Niloofar polish: '{(story.title_fa or '')[:40]}'")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"Niloofar polish failed for story {story.id}: {e}")

    logger.info(f"Niloofar polish telegram: {stats}")
    return stats


async def step_backfill_diaspora_ogimages():
    """Pull og:image from diaspora-outlet article URLs when the stored
    image_url is missing or obviously bad (icon, expired telesco.pe,
    broken iranintl hash).

    Scoped to diaspora (production_location='outside_iran') outlets
    because:
      - Railway's IP can reach BBC Persian, Iran International, Euronews,
        Radio Farda, DW, RFI, Kayhan London, etc. without geo-blocks.
      - Inside-Iran state/semi-state sites (irna, press-tv, tasnim,
        mehrnews, etc.) actively geo-block Railway and return either 403
        or a captcha page — pulling their og:image from outside Iran
        just wastes request budget.
      - Telegram posts are skipped entirely (they have no article URL
        and telesco.pe CDN expires).

    Attribution: source.name_fa becomes the photo credit line. Frontend
    already reads a `manual_image_credit` key from summary_en when set
    via the HITL pin-image flow; we reuse the same mechanism here so
    the reader sees «عکس: بی‌بی‌سی فارسی» etc. under the cover image.

    Idempotent: each write sets image_checked_at so a retry skips
    articles already processed in the last 24h. Capped at 200 articles
    per run to stay inside the step timeout.
    """
    from sqlalchemy import and_, or_, select

    from app.database import async_session
    from app.models.article import Article
    from app.models.source import Source
    from app.services.nlp_pipeline import _fetch_og_image

    # Mirror the "bad image" heuristic from app.api.v1.stories so we
    # target exactly the URLs the frontend scorer would reject.
    BAD_FRAGMENTS = (
        "ico-192x192", "ico-512x512", "webapp/ico-", "manifest-icon",
        "favicon", "apple-touch-icon", "/logo.", "/icon.",
        ".ico", ".svg", "telesco.pe", "cdn.telegram",
        "google.com/s2/favicons",
    )

    stats = {
        "checked": 0, "found_ogimage": 0, "replaced_null": 0,
        "replaced_bad": 0, "no_ogimage": 0, "errors": 0,
    }

    async with async_session() as db:
        # Candidates: diaspora articles with missing or "bad-looking" URLs
        # that haven't been re-checked in the last 24h.
        recheck_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Build a SQL OR clause covering each bad-URL fragment + null.
        bad_url_conditions = [Article.image_url.is_(None)]
        for frag in BAD_FRAGMENTS:
            bad_url_conditions.append(Article.image_url.contains(frag))
        # iranintl bare-hash URLs (no -WxH.ext) — detect by negation
        # inside Python after fetching; too complex to express in SQL.

        result = await db.execute(
            select(Article)
            .join(Source, Article.source_id == Source.id)
            .where(
                Source.production_location == "outside_iran",
                Source.is_active.is_(True),
                or_(*bad_url_conditions),
                or_(
                    Article.image_checked_at.is_(None),
                    Article.image_checked_at < recheck_cutoff,
                ),
            )
            .order_by(Article.ingested_at.desc())
            .limit(200)
        )
        articles = list(result.scalars().all())

    if not articles:
        return stats

    now_ts = datetime.now(timezone.utc)

    # Process in small batches with short sessions so a long run doesn't
    # hold one Neon connection for 10+ minutes and get killed.
    BATCH = 20
    for i in range(0, len(articles), BATCH):
        chunk = articles[i : i + BATCH]
        updates: list[tuple[str, str | None]] = []  # (article_id, new_url)

        for art in chunk:
            stats["checked"] += 1
            try:
                og_url = await _fetch_og_image(art.url)
            except Exception:
                stats["errors"] += 1
                og_url = None

            if og_url:
                # Reject obvious icons / broken patterns from the og:image too
                low = og_url.lower()
                if any(f in low for f in BAD_FRAGMENTS):
                    og_url = None

            if og_url:
                stats["found_ogimage"] += 1
                if art.image_url is None:
                    stats["replaced_null"] += 1
                else:
                    stats["replaced_bad"] += 1
                updates.append((str(art.id), og_url))
            else:
                stats["no_ogimage"] += 1
                # Stamp the checked_at anyway so we don't re-try tomorrow
                updates.append((str(art.id), None))

        async with async_session() as db:
            from sqlalchemy import update as _upd

            for article_id, new_url in updates:
                values: dict = {"image_checked_at": now_ts}
                if new_url:
                    values["image_url"] = new_url
                await db.execute(
                    _upd(Article).where(Article.id == article_id).values(**values)
                )
            await db.commit()

    logger.info(f"Diaspora og:image backfill: {stats}")
    return stats


async def step_migrate_images_to_r2():
    """Download source-CDN article images and re-host them on R2.

    Why: several Iran-hosted media (irna.ir, tabnak.ir, tasnimnews.com…)
    geo-block non-Iran IPs. When Vercel's `/_next/image` tries to proxy
    their CDNs from US/EU edge IPs, the upstream fetch fails and the
    homepage shows placeholders. Copying every article image onto R2
    at ingest time removes the runtime dependency on origin reachability
    — the frontend always loads from our own CDN.

    Idempotent via the existing `_object_exists_in_r2` short-circuit in
    `download_image`. Capped at 300 articles per run so a single
    maintenance pass stays under the step timeout; most-recent articles
    go first so new content lands on R2 before it surfaces on the
    homepage. Articles whose source download fails are left alone
    (SafeImage's per-source geoblock bypass remains the fallback).
    """
    from sqlalchemy import select, not_, update
    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.services.image_downloader import download_image, LOCAL_IMAGE_BASE

    stats = {"migrated": 0, "skipped": 0, "failed": 0, "no_config": 0}

    if not settings.r2_public_url:
        logger.warning("R2 not configured — skipping migrate_images_r2")
        stats["no_config"] = 1
        return stats

    r2_prefix = settings.r2_public_url.rstrip("/")

    # Pull the work list in a short read session, then close it. Downloading
    # 300 images takes ~15 min, and Neon/asyncpg close the connection well
    # before that — a single long-held session + deferred commit loses the
    # whole batch (as happened 2026-04-18: 249 R2 uploads, 0 DB updates).
    async with async_session() as db:
        result = await db.execute(
            select(Article.id, Article.image_url)
            .where(
                Article.image_url.isnot(None),
                Article.image_url != "",
                not_(Article.image_url.like(f"{r2_prefix}%")),
                not_(Article.image_url.like(f"{LOCAL_IMAGE_BASE}%")),
            )
            .order_by(Article.ingested_at.desc())
            .limit(300)
        )
        work = [(row.id, row.image_url) for row in result.all()]

    # Commit in small batches so partial progress survives a mid-run crash,
    # and no session stays idle while the network does the heavy lifting.
    BATCH = 25
    pending: list[tuple] = []  # (article_id, new_url)

    async def _flush():
        if not pending:
            return
        async with async_session() as db:
            for article_id, new_url in pending:
                await db.execute(
                    update(Article).where(Article.id == article_id).values(image_url=new_url)
                )
            await db.commit()
        pending.clear()

    from app.services import maintenance_state as _ms
    total_n = len(work)
    for idx, (article_id, old_url) in enumerate(work):
        if idx % 5 == 0:
            _ms.update_step_progress(idx, total_n, label="downloading + uploading to R2")
        stored = await download_image(old_url)
        if stored and stored != old_url:
            pending.append((article_id, stored))
            stats["migrated"] += 1
            if len(pending) >= BATCH:
                await _flush()
        elif stored:
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    await _flush()
    _ms.update_step_progress(total_n, total_n, label="R2 migration done")

    logger.info(f"Migrate images R2: {stats}")
    return stats


async def step_backfill_analyst_counts():
    """Resolve `supporters` → analyst channel IDs for every story's existing
    telegram_analysis, writing real `supporter_count` / `analysts_total` /
    `pct` onto each prediction.

    Why: pass-2 used to leak `"pct": 40` from the prompt example straight
    into every prediction. No LLM call is needed to fix historical rows —
    we just resolve the LLM's free-text supporter names against the
    TelegramChannel table. Cheap.

    Runs in the full pipeline + can be triggered ad-hoc from the admin
    API. Idempotent; safe to re-run.
    """
    from sqlalchemy import select, update
    from app.database import async_session
    from app.models.story import Story
    from app.services.telegram_analysis import enrich_predictions_with_analyst_counts

    stats = {"updated": 0, "skipped": 0, "no_analysis": 0}

    async with async_session() as db:
        result = await db.execute(
            select(Story).where(Story.telegram_analysis.isnot(None))
        )
        stories = list(result.scalars().all())

    for story in stories:
        analysis = story.telegram_analysis
        if not analysis or not isinstance(analysis, dict):
            stats["no_analysis"] += 1
            continue

        preds = analysis.get("predictions") or []
        if not preds:
            stats["skipped"] += 1
            continue

        async with async_session() as db:
            enriched = dict(analysis)
            enriched["predictions"] = [dict(p) if isinstance(p, dict) else p for p in preds]
            await enrich_predictions_with_analyst_counts(db, enriched)

            # Propagate the counts to predictions_display too — Niloofar's
            # polish step keeps its own copies of each prediction dict
            # (polished text + preserved metadata), built positionally from
            # the raw predictions list.
            disp = enriched.get("predictions_display")
            if isinstance(disp, list):
                for i, d in enumerate(disp):
                    if not isinstance(d, dict):
                        continue
                    raw = enriched["predictions"][i] if i < len(enriched["predictions"]) else None
                    if isinstance(raw, dict):
                        for k in ("supporter_count", "analysts_total", "pct"):
                            if k in raw:
                                d[k] = raw[k]

            await db.execute(
                update(Story).where(Story.id == story.id).values(telegram_analysis=enriched)
            )
            await db.commit()
            stats["updated"] += 1

    logger.info(f"Backfill analyst counts: {stats}")
    return stats


FULL_PIPELINE = [
    ("ingest", "Ingest RSS + Telegram (may take 10-20 min)", "step_ingest"),
    ("prune_noise", "Drop too-short Telegram posts/articles before NLP", "step_prune_noise"),
    ("recount", "Recount article_count / source_count from attached rows", "step_recount_stories"),
    ("classify_content_type", "Classify content type (news / opinion / discussion / aggregation / other)", "step_classify_content_type"),
    ("process", "NLP process (embed, translate, extract)", "step_process"),
    ("backfill_farsi_titles", "Backfill Farsi titles", "step_backfill_farsi_titles"),
    ("cluster", "Cluster articles into stories", "step_cluster"),
    ("centroids", "Recompute story centroid embeddings", "step_recompute_centroids"),
    ("recluster_orphans", "Second-chance clustering for 6h+ orphans (looser cosine)", "step_recluster_orphans"),
    ("telegram_link", "Link Telegram posts to stories (embeddings)", "step_telegram_link_posts"),
    # Fix stale mis-links: posts whose best-match story has drifted
    # since they were first attached get moved to where they actually
    # belong now. Runs after new posts are linked so reassignment
    # considers the freshest centroids. Invalidates affected stories'
    # telegram_analysis cache so the next read regenerates cleanly.
    ("telegram_reassign", "Reassign drifted Telegram posts to better-matching stories", "step_telegram_reassign_posts"),
    ("merge_similar", "Merge similar visible stories", "step_merge_similar"),
    ("summarize", "Summarize new stories", "step_summarize"),
    ("bias_score", "Bias scoring", "step_bias_score"),
    ("fix_images", "Fix broken images", "step_fix_images"),
    # Pull og:image from diaspora-outlet article URLs when image_url is
    # null or an obvious icon/telesco.pe dead-link. Runs BEFORE
    # migrate_images_r2 so the newly-fetched URLs get uploaded to R2
    # in the same maintenance pass.
    ("diaspora_ogimages", "Backfill diaspora article og:images", "step_backfill_diaspora_ogimages"),
    ("migrate_images_r2", "Migrate source-CDN images to R2 (up to 300/run)", "step_migrate_images_to_r2"),
    # Rescue stories whose auto-picked image resolves to null/icon/broken —
    # writes a manual_image_url pointing at the best valid article image.
    ("niloofar_image_rescue", "Niloofar rescues stories with bad cover images", "step_niloofar_image_rescue"),
    ("story_quality", "Story quality checks", "step_story_quality"),
    ("detect_silences", "Detect coverage silences", "step_detect_silences"),
    ("detect_coordination", "Detect coordinated messaging", "step_detect_coordination"),
    ("source_health", "Source health", "step_source_health"),
    ("prune_stagnant", "Prune 1-article (>48h) and 2-4-article (>14d) stagnant stories", "step_prune_stagnant"),
    ("demote_umbrellas", "Demote umbrella stories (>21d old + >100 articles)", "step_demote_umbrella_stories"),
    ("archive_stale", "Archive stale stories", "step_archive_stale"),
    ("recalc_trending", "Recalculate trending", "step_recalculate_trending"),
    ("dedup_articles", "Dedup articles", "step_deduplicate_articles"),
    ("fixes", "Auto-fix common issues", "step_fix_issues"),
    ("flag_unrelated", "Auto-flag unrelated articles", "step_flag_unrelated_articles"),
    ("image_relevance", "Image relevance check", "step_image_relevance"),
    ("analyst_takes", "Extract analyst takes from Telegram", "step_extract_analyst_takes"),
    ("verify_predictions", "Verify analyst predictions", "step_verify_predictions"),
    ("rater_feedback", "Apply rater feedback", "step_rater_feedback_apply"),
    ("summary_corrections", "Regenerate story summaries from rater corrections", "step_apply_summary_corrections"),
    ("niloofar_feedback_audit", "Niloofar audits open «نامرتبط» queue", "step_niloofar_feedback_audit"),
    ("age_out_stale_feedback", "Mark unconverged anonymous flags wont_do (#9)", "step_age_out_stale_feedback"),
    ("source_trust", "Recompute Source.cluster_quality_score from feedback", "step_source_trust_recompute"),
    ("feedback_health", "Feedback system health", "step_feedback_health"),
    ("telegram_analysis", "Deep Telegram discourse analysis (two-pass)", "step_telegram_deep_analysis"),
    ("backfill_analyst_counts", "Resolve prediction supporters → analyst counts (no LLM)", "step_backfill_analyst_counts"),
    ("telegram_health", "Telegram session health", "step_telegram_health"),
    ("visual", "Visual check", "step_visual_check"),
    ("uptime", "Uptime check", "step_uptime_check"),
    ("disk", "Disk monitoring", "step_disk_monitoring"),
    ("cost_tracking", "LLM cost tracking", "step_cost_tracking"),
    ("backup", "Database backup", "step_database_backup"),
    ("quality_postprocess", "Quality post-processing (LLM review)", "step_quality_postprocess"),
    ("editorial", "Editorial context blurb for top stories", "step_editorial"),
    ("niloofar_polish_telegram", "Niloofar polishes Telegram predictions/claims for homepage", "step_niloofar_polish_telegram"),
    ("snapshot_analyses", "Snapshot analysis axes for daily-change detection", "step_snapshot_analyses"),
    ("audit_clusters", "Cluster coherence audit (flag drift for Niloofar review)", "step_audit_cluster_coherence"),
    # Same hourly detection the rss-cron runs. The daily full run lands at
    # 04:00 UTC which the rss-cron skips on purpose (collision slot), so
    # including it here keeps the signal fresh at that hour too.
    ("detect_hourly_updates", "Flag significant intra-day story updates", "step_detect_hourly_updates"),
    ("weekly_digest", "Weekly digest", "step_weekly_digest"),
    ("worldview_digests", "Weekly worldview synthesis (4 bundles)", "step_worldview_digests"),
]

# Lightweight pipeline for the ingest-only cron — keeps the homepage fresh
# between daily full runs without the heavy LLM-per-article work.
INGEST_ONLY_PIPELINE = [
    ("ingest", "Ingest RSS + Telegram", "step_ingest"),
    ("prune_noise", "Drop too-short Telegram posts/articles before NLP", "step_prune_noise"),
    ("recount", "Recount article_count / source_count from attached rows", "step_recount_stories"),
    ("classify_content_type", "Classify content type (news / opinion / discussion / aggregation / other)", "step_classify_content_type"),
    ("process", "NLP process (embed, translate, extract)", "step_process"),
    ("backfill_farsi_titles", "Backfill Farsi titles", "step_backfill_farsi_titles"),
    ("cluster", "Cluster articles into stories", "step_cluster"),
    ("centroids", "Recompute story centroid embeddings", "step_recompute_centroids"),
    ("recluster_orphans", "Second-chance clustering for 6h+ orphans (looser cosine)", "step_recluster_orphans"),
    ("telegram_link", "Link Telegram posts to stories (embeddings)", "step_telegram_link_posts"),
    # Keeps newly-ingested images on R2 so the homepage never depends on
    # the origin CDN being reachable from Vercel. Idempotent, capped 300/run.
    ("migrate_images_r2", "Migrate source-CDN images to R2 (up to 300/run)", "step_migrate_images_to_r2"),
    # Same hourly update detection the rss-cron runs. Keeping it here too
    # means the signal refreshes on the 4 hours rss-cron skips by design
    # (00/06/12/18 UTC — the ingest-cron collision slots).
    ("detect_hourly_updates", "Flag significant intra-day story updates", "step_detect_hourly_updates"),
]

# Hourly pipeline — RSS-only. Designed to run every hour from 6am to
# midnight Paris time (04:00–21:00 UTC). Skips Telegram (slow) and
# everything LLM-heavy; focuses on getting new articles clustered and
# detecting intra-day story updates for the "بروزرسانی" badge.
HOURLY_PIPELINE = [
    ("ingest_rss", "RSS-only ingest (no Telegram)", "step_ingest_rss"),
    ("classify_content_type", "Classify content type (news / opinion / discussion / aggregation / other)", "step_classify_content_type"),
    ("process", "NLP process (embed, translate, extract)", "step_process"),
    ("cluster", "Cluster new articles into stories", "step_cluster"),
    ("centroids", "Recompute story centroid embeddings", "step_recompute_centroids"),
    ("detect_hourly_updates", "Flag significant intra-day story updates", "step_detect_hourly_updates"),
    # F8 — fast source-trust pass. No-ops when no flags landed in the
    # last hour, so this adds < 100ms to most runs.
    ("source_trust_fast", "Fast source-trust check on hourly flags", "step_source_trust_fast"),
]


async def run_maintenance(mode: str = "full"):
    """Run maintenance pipeline.

    mode="full"   → FULL_PIPELINE (~33 steps, daily at 04:00)
    mode="ingest" → INGEST_ONLY_PIPELINE (~6 cheap steps, intended to run
                    every 2-3 hours between the daily full run)
    mode="hourly" → HOURLY_PIPELINE (RSS-only, 5 steps, runs hourly 6am–
                    midnight Paris for intra-day update detection)
    """
    from app.services import maintenance_state

    start = time.time()
    if mode == "full":
        pipeline_spec = FULL_PIPELINE
    elif mode == "hourly":
        pipeline_spec = HOURLY_PIPELINE
    else:
        pipeline_spec = INGEST_ONLY_PIPELINE
    # Resolve step callables by name (they're defined above in this module)
    pipeline = [(key, display, globals()[func_name]) for key, display, func_name in pipeline_spec]

    logger.info("=" * 50)
    logger.info(f"Maintenance started at {datetime.now().strftime('%Y-%m-%d %H:%M')} (mode={mode}, steps={len(pipeline)})")
    logger.info("=" * 50)

    maintenance_state.start_run(total_steps=len(pipeline))
    results = {}

    try:
        for key, display, func in pipeline:
            maintenance_state.begin_step(display)
            timeout = STEP_TIMEOUTS_SEC.get(key, DEFAULT_STEP_TIMEOUT_SEC)
            try:
                result = await asyncio.wait_for(func(), timeout=timeout)
                results[key] = result
                maintenance_state.end_step(display, "ok", result)
            except asyncio.TimeoutError:
                logger.error(f"{display} timed out after {timeout}s — continuing")
                err = {"error": f"timeout after {timeout}s"}
                results[key] = err
                maintenance_state.end_step(display, "error", err)
            except Exception as e:
                logger.error(f"{display} failed: {e}")
                err = {"error": str(e)}
                results[key] = err
                maintenance_state.end_step(display, "error", err)

        # Doc update is full-pipeline-only; skip in ingest-only mode.
        if mode == "full":
            maintenance_state.begin_step("Update project docs")
            try:
                results["docs"] = await asyncio.wait_for(
                    step_update_docs(results, start),
                    timeout=DEFAULT_STEP_TIMEOUT_SEC,
                )
                maintenance_state.end_step("Update project docs", "ok", results["docs"])
            except asyncio.TimeoutError:
                logger.error("Doc update timed out — continuing")
                err = {"error": f"timeout after {DEFAULT_STEP_TIMEOUT_SEC}s"}
                results["docs"] = err
                maintenance_state.end_step("Update project docs", "error", err)
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

        # Persist log to database so it survives container restarts
        try:
            import json as _json
            import uuid as _uuid
            from app.database import async_session as _as
            from sqlalchemy import text as _text
            async with _as() as _db:
                await _db.execute(_text(
                    "INSERT INTO maintenance_logs (id, run_at, status, elapsed_s, results, steps) "
                    "VALUES (:id, NOW(), 'success', :elapsed, :results, :steps)"
                ), {
                    "id": _uuid.uuid4(),
                    "elapsed": round(elapsed, 1),
                    "results": _json.dumps(results, ensure_ascii=False, default=str),
                    "steps": _json.dumps(
                        [
                            {
                                "name": s["name"],
                                "status": s["status"],
                                "elapsed_s": s["elapsed_s"],
                                # Preserve stats — for failed steps this is
                                # `{"error": "<message>"}` from the harness, so
                                # the dashboard / curl output can show what went
                                # wrong without scrolling Railway logs.
                                "stats": s.get("stats"),
                            }
                            for s in maintenance_state.STATE.get("steps", [])
                        ],
                        ensure_ascii=False,
                        default=str,
                    ),
                })
                await _db.commit()
                logger.info("Maintenance log persisted to database")
        except Exception as log_err:
            logger.warning(f"Failed to persist maintenance log: {log_err}")

        return results

    except Exception as e:
        logger.exception("Maintenance run crashed")
        maintenance_state.finish_run(
            "error", results=results, error=str(e), total_elapsed_s=time.time() - start
        )

        # Persist error log too
        try:
            import json as _json
            import uuid as _uuid
            from app.database import async_session as _as
            from sqlalchemy import text as _text
            async with _as() as _db:
                await _db.execute(_text(
                    "INSERT INTO maintenance_logs (id, run_at, status, elapsed_s, results, error) "
                    "VALUES (:id, NOW(), 'error', :elapsed, :results, :error)"
                ), {
                    "id": _uuid.uuid4(),
                    "elapsed": round(time.time() - start, 1),
                    "results": _json.dumps(results, ensure_ascii=False, default=str),
                    "error": str(e),
                })
                await _db.commit()
        except Exception:
            pass

        raise


def _run_once(mode: str) -> None:
    """One maintenance invocation with lock semantics — both runtime paths
    (single-shot CLI and --loop) go through this."""
    label = f"{mode}@{datetime.now().strftime('%H:%M:%S')}"
    if not try_acquire_lock(label):
        logger.warning(
            "Another maintenance run holds the lock — skipping this firing (mode=%s)",
            mode,
        )
        return
    try:
        asyncio.run(run_maintenance(mode=mode))
    finally:
        release_lock()


def main():
    parser = argparse.ArgumentParser(description="Doornegar Auto-Maintenance")
    parser.add_argument("--loop", type=float, help="Run every N hours (omit for single run)")
    parser.add_argument(
        "--mode",
        choices=("full", "ingest", "hourly"),
        default="full",
        help="full = complete 34-step pipeline (daily). ingest = lightweight "
             "6-step pipeline (every 6h). hourly = RSS-only 5-step pipeline "
             "for intra-day updates (every hour 6am–midnight Paris).",
    )
    args = parser.parse_args()

    if args.loop:
        interval = args.loop * 3600
        logger.info(f"Starting maintenance loop — every {args.loop}h (mode={args.mode})")
        while True:
            _run_once(args.mode)
            logger.info(f"Next run in {args.loop}h...")
            time.sleep(interval)
    else:
        _run_once(args.mode)


if __name__ == "__main__":
    main()

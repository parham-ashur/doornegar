"""RSS feed ingestion service.

Fetches articles from configured news sources via RSS feeds,
extracts article content, and stores them in the database.
"""

import logging
from datetime import datetime, timezone

import feedparser
import httpx
from langdetect import detect
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from trafilatura import extract

from app.config import settings
from app.models.article import Article
from app.models.ingestion_log import IngestionLog
from app.models.source import Source

logger = logging.getLogger(__name__)


async def fetch_feed(feed_url: str) -> feedparser.FeedParserDict | None:
    """Fetch and parse an RSS feed."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.ingestion_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            return feedparser.parse(response.text)
    except Exception as e:
        logger.error(f"Failed to fetch feed {feed_url}: {e}")
        return None


async def extract_article_content(url: str) -> str | None:
    """Fetch full article page and extract main text content."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.ingestion_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/0.1)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return extract(response.text, include_comments=False, include_tables=False)
    except Exception as e:
        logger.warning(f"Failed to extract content from {url}: {e}")
        return None


def detect_language(text: str) -> str:
    """Detect language of text, defaulting to 'fa'."""
    try:
        lang = detect(text)
        return "fa" if lang in ("fa", "ar") else lang
    except Exception:
        return "fa"


def parse_published_date(entry: dict) -> datetime | None:
    """Extract published date from a feed entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                from time import mktime
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except Exception:
                continue
    return None


async def ingest_source(source: Source, db: AsyncSession) -> dict:
    """Ingest all RSS feeds for a single source.

    Returns dict with counts: {found, new, errors}.
    """
    stats = {"found": 0, "new": 0, "errors": 0}
    rss_urls = source.rss_urls if isinstance(source.rss_urls, list) else []

    for feed_url in rss_urls:
        started_at = datetime.now(timezone.utc)
        log = IngestionLog(
            source_id=source.id,
            feed_url=feed_url,
            status="success",
            started_at=started_at,
        )

        try:
            feed = await fetch_feed(feed_url)
            if not feed or not feed.entries:
                log.status = "error"
                log.error_message = "No entries found or feed unavailable"
                db.add(log)
                stats["errors"] += 1
                continue

            entries = feed.entries[: settings.max_articles_per_feed]
            log.articles_found = len(entries)

            new_count = 0
            for entry in entries:
                url = entry.get("link", "").strip()
                if not url:
                    continue

                title = entry.get("title", "").strip()
                if not title:
                    continue

                summary = entry.get("summary", entry.get("description", "")).strip()
                image_url = None
                if "media_content" in entry and entry["media_content"]:
                    image_url = entry["media_content"][0].get("url")
                elif "enclosures" in entry and entry["enclosures"]:
                    image_url = entry["enclosures"][0].get("href")

                language = detect_language(title)
                published_at = parse_published_date(entry)

                # Upsert: skip if URL already exists
                stmt = (
                    insert(Article)
                    .values(
                        source_id=source.id,
                        title_original=title,
                        url=url,
                        summary=summary or None,
                        image_url=image_url,
                        author=entry.get("author"),
                        language=language,
                        published_at=published_at,
                    )
                    .on_conflict_do_nothing(index_elements=["url"])
                    .returning(Article.id)
                )
                result = await db.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    new_count += 1

            log.articles_new = new_count
            stats["found"] += log.articles_found
            stats["new"] += new_count

        except Exception as e:
            log.status = "error"
            log.error_message = str(e)[:500]
            stats["errors"] += 1
            logger.exception(f"Error ingesting {feed_url}")

        log.completed_at = datetime.now(timezone.utc)
        db.add(log)

    return stats


async def ingest_all_sources(db: AsyncSession) -> dict:
    """Ingest articles from all active sources.

    Returns aggregate stats.
    """
    result = await db.execute(
        select(Source).where(Source.is_active.is_(True))
    )
    sources = result.scalars().all()

    total_stats = {"found": 0, "new": 0, "errors": 0, "scraped": 0, "sources": len(sources)}
    for source in sources:
        logger.info(f"Ingesting source: {source.slug}")
        source_stats = await ingest_source(source, db)
        total_stats["found"] += source_stats["found"]
        total_stats["new"] += source_stats["new"]
        total_stats["errors"] += source_stats["errors"]

        # Fallback: if RSS failed, try scraping
        if source_stats["found"] == 0 and source_stats["errors"] > 0:
            try:
                from app.services.scraper import scrape_source
                scraped = await scrape_source(source.slug)
                for article_data in scraped:
                    stmt = (
                        insert(Article)
                        .values(
                            source_id=source.id,
                            title_original=article_data["title"],
                            url=article_data["url"],
                            language=detect_language(article_data["title"]),
                            published_at=article_data.get("published_at"),
                        )
                        .on_conflict_do_nothing(index_elements=["url"])
                        .returning(Article.id)
                    )
                    result = await db.execute(stmt)
                    if result.scalar_one_or_none() is not None:
                        total_stats["scraped"] += 1
                if scraped:
                    logger.info(f"Scraped {len(scraped)} articles from {source.slug}")
            except Exception as e:
                logger.warning(f"Scraping fallback failed for {source.slug}: {e}")

    await db.commit()
    logger.info(
        f"Ingestion complete: {total_stats['new']} new articles "
        f"from {total_stats['sources']} sources"
    )
    return total_stats

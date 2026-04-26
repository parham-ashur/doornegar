"""RSS feed ingestion service.

Fetches articles from configured news sources via RSS feeds,
extracts article content, and stores them in the database.
"""

import logging
import re
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

# Per-source URL-path exclusions. Keyed by source slug; each value is a
# list of path substrings. If any substring appears in the article URL,
# the article is skipped at ingest. Intended to drop sports, entertain-
# ment, lifestyle, horoscope, and weather stories from Iranian general-
# news outlets whose RSS dumps everything. These sections bloat the
# article pool without ever clustering with other sources' coverage of
# the same topic, so they become stagnant 1-2 article stories.
#
# Add patterns gradually — false positives hurt more than false
# negatives here. Check the source's real URL structure before adding.
SOURCE_URL_EXCLUSIONS: dict[str, list[str]] = {
    "shargh": ["/sport", "/entertainment", "/art-culture", "/life-style"],
    "irna": ["/sport", "/entertainment", "/art-culture", "/life"],
    "khabar-online": ["/sport/", "/entertainment/", "/life/"],
    "mehr-news": ["/news/sport", "/news/entertainment", "/news/art"],
    "ilna": ["/بخش-ورزش", "/بخش-فرهنگ-هنر", "/بخش-سبک-زندگی"],
    "tabnak": ["/fa/news/sport", "/fa/news/entertainment"],
    "fars-news": ["/sport/", "/entertainment/"],
    "tasnim": ["/sport/", "/art-culture/"],
    "etemad": ["/sport/", "/entertainment/"],
    "entekhab": ["/fa/news/sport", "/fa/news/entertainment"],
    "isna": ["/sport/", "/art-culture/"],
    "etemad-online": ["/بخش-ورزش", "/بخش-فرهنگ"],
}


def _url_excluded(url: str, source_slug: str | None) -> bool:
    """Return True when the URL matches the source's exclusion list."""
    if not source_slug:
        return False
    patterns = SOURCE_URL_EXCLUSIONS.get(source_slug)
    if not patterns:
        return False
    return any(p in url for p in patterns)


# URL patterns for favicons, PWA icons, and other non-article thumbnails
# that RSS feeds sometimes expose as media_content when no real article
# image exists. Matches the frontend SafeImage filter so rejected URLs
# never enter the DB in the first place — the frontend filter stays as
# a safety net for URLs already stored from earlier ingests.
_ICON_URL_PATTERNS = [
    re.compile(r"/ico-\d+x\d+\.(png|jpg|webp|svg)(\?|$)", re.I),
    re.compile(r"/favicon[.\-]", re.I),
    re.compile(r"/icon[.\-]\d+", re.I),
    re.compile(r"/apple-touch-icon", re.I),
    re.compile(r"/webApp/ico-", re.I),
    re.compile(r"/manifest-icon", re.I),
]


def _is_icon_like(url: str | None) -> bool:
    """Return True when a URL is almost certainly a site icon, not an
    article image. Used at ingest time to reject before the DB write."""
    if not url:
        return False
    return any(p.search(url) for p in _ICON_URL_PATTERNS)


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


def _extract_rss_category(entry: dict) -> str | None:
    """Pull a category/section label from an RSS entry.

    feedparser exposes <category> as either entry.tags (list of dicts
    with 'term') or entry.category (string). Both forms occur across
    Iranian outlets. Returns the first non-empty label, lowercased and
    trimmed; None if absent.
    """
    tags = entry.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                label = (tag.get("term") or tag.get("label") or "").strip()
                if label:
                    return label[:120]
    raw = entry.get("category")
    if isinstance(raw, str):
        label = raw.strip()
        if label:
            return label[:120]
    return None


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
            skipped_url = 0
            for entry in entries:
                url = entry.get("link", "").strip()
                if not url:
                    continue

                # Skip sections we don't cover (sport/entertainment/
                # lifestyle on big Iranian news outlets). These were
                # creating 1-2 article stagnant stories and bloating
                # the hidden-story count.
                if _url_excluded(url, source.slug):
                    skipped_url += 1
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
                # Try media:thumbnail
                if not image_url and "media_thumbnail" in entry and entry["media_thumbnail"]:
                    image_url = entry["media_thumbnail"][0].get("url")
                # Try entry.image (some feeds use <image> tag)
                if not image_url:
                    img_field = entry.get("image")
                    if isinstance(img_field, dict) and img_field.get("href"):
                        image_url = img_field["href"]
                    elif isinstance(img_field, str) and img_field.strip():
                        image_url = img_field.strip()
                # Try og:image from link tags in feed
                if not image_url and "links" in entry:
                    for link in entry["links"]:
                        if link.get("type", "").startswith("image/"):
                            image_url = link.get("href")
                            break
                # Fallback: extract first <img> from summary or content HTML
                if not image_url:
                    image_url = _extract_image_from_html(
                        entry.get("summary", ""),
                        entry.get("content", []),
                    )
                # Reject favicons / app-icons captured from feeds that expose
                # the site's web-app icon as media_content. Better to store
                # NULL and render the newspaper placeholder than to show a
                # stretched 192×192 logo on a 16:9 card.
                if _is_icon_like(image_url):
                    image_url = None

                language = detect_language(title)
                published_at = parse_published_date(entry)
                rss_category = _extract_rss_category(entry)

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
                        rss_category=rss_category,
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
            if skipped_url:
                logger.info(f"  {source.slug}: skipped {skipped_url} URLs matching exclusion patterns")

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
        try:
            source_stats = await ingest_source(source, db)
        except Exception as e:
            logger.exception(f"Source {source.slug} crashed during ingest: {e}")
            total_stats["errors"] += 1
            continue
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


import re

# Patterns in image URLs that indicate non-article images
_SKIP_PATTERNS = (
    "logo", "icon", "favicon", "avatar", "pixel", "tracking",
    "spacer", "blank", "transparent", "1x1", "badge", "sprite",
    "ads", "widget", "button", "spinner", "gravatar", "emoji",
)


def _extract_image_from_html(summary: str, content_list: list) -> str | None:
    """Extract the first likely article image from RSS summary or content HTML.

    Checks both the summary field and the content list (used by Atom feeds).
    Skips tiny icons, tracking pixels, and logos.
    """
    # Combine HTML sources to search
    html_parts = []
    if summary:
        html_parts.append(summary)
    if content_list:
        for content_item in content_list:
            if isinstance(content_item, dict):
                html_parts.append(content_item.get("value", ""))
            elif isinstance(content_item, str):
                html_parts.append(content_item)

    html_text = " ".join(html_parts)
    if not html_text or "<img" not in html_text.lower():
        return None

    # Use regex to avoid importing BeautifulSoup in the hot ingestion path
    img_tags = re.findall(r'<img[^>]+>', html_text, re.IGNORECASE)
    for img_tag in img_tags[:10]:  # only check first 10 images
        # Extract src attribute
        src_match = re.search(r'src=["\']([^"\']+)["\']', img_tag, re.IGNORECASE)
        if not src_match:
            continue
        src = src_match.group(1).strip()
        if not src or src.startswith("data:"):
            continue

        src_lower = src.lower()

        # Skip known non-article image patterns
        if any(p in src_lower for p in _SKIP_PATTERNS):
            continue

        # Skip tiny images by checking width/height attributes
        width_match = re.search(r'width=["\']?(\d+)', img_tag, re.IGNORECASE)
        height_match = re.search(r'height=["\']?(\d+)', img_tag, re.IGNORECASE)
        if width_match and int(width_match.group(1)) < 100:
            continue
        if height_match and int(height_match.group(1)) < 100:
            continue

        # Must be an absolute URL (RSS feeds usually have absolute URLs)
        if src.startswith(("http://", "https://")):
            return src

    return None

"""Telegram public channel monitoring service.

Fetches posts from public Telegram channels, links them to news stories
(by URL matching or embedding similarity), and analyzes sentiment/framing.

Uses Telethon library for Telegram API access. Requires a Telegram API
ID and hash (free from https://my.telegram.org).
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.social import SocialSentimentSnapshot, TelegramChannel, TelegramPost
from app.models.source import Source
from app.models.story import Story
from app.nlp.persian import extract_keywords, normalize

logger = logging.getLogger(__name__)

# Lazy-loaded Telethon client
_client = None


async def _get_telegram_client():
    """Get or create the Telethon client."""
    global _client
    if _client is not None and _client.is_connected():
        return _client

    try:
        from telethon import TelegramClient

        _client = TelegramClient(
            "doornegar_session",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await _client.connect()
        if not await _client.is_user_authorized():
            raise RuntimeError("Telegram session not authorized. Run phone auth first.")
        logger.info("Telegram client connected")
        return _client
    except ImportError:
        raise RuntimeError("telethon not installed. Install with: pip install telethon")
    except Exception as e:
        logger.error(f"Failed to connect Telegram client: {e}")
        raise


def extract_urls_from_text(text: str) -> list[str]:
    """Extract URLs from a Telegram post text."""
    if not text:
        return []
    url_pattern = re.compile(
        r"https?://[^\s<>\"')\]،؛]+",
        re.IGNORECASE,
    )
    urls = url_pattern.findall(text)
    # Clean trailing punctuation
    cleaned = []
    for url in urls:
        url = url.rstrip(".,;:!?)")
        if len(url) > 10:  # Skip very short URLs
            cleaned.append(url)
    return cleaned


def normalize_url(url: str) -> str:
    """Normalize a URL for matching against stored article URLs."""
    parsed = urlparse(url)
    # Remove www. prefix, trailing slashes, and query params for matching
    hostname = parsed.hostname or ""
    hostname = hostname.replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{hostname}{path}".lower()


async def fetch_channel_posts(
    channel_username: str,
    limit: int = 50,
    min_id: int | None = None,
) -> list[dict]:
    """Fetch recent posts from a public Telegram channel.

    Returns list of dicts with post data.
    """
    client = await _get_telegram_client()

    try:
        from telethon.tl.functions.messages import GetHistoryRequest

        entity = await client.get_entity(channel_username)
        posts = []

        async for message in client.iter_messages(
            entity,
            limit=limit,
            min_id=min_id or 0,
        ):
            if not message.text and not message.message:
                continue

            text = message.text or message.message or ""
            urls = extract_urls_from_text(text)

            # Get view/forward/reply counts
            views = getattr(message, "views", None)
            forwards = getattr(message, "forwards", None)
            reply_count = None
            if hasattr(message, "replies") and message.replies:
                reply_count = message.replies.replies

            posts.append({
                "message_id": message.id,
                "text": text,
                "date": message.date,
                "views": views,
                "forwards": forwards,
                "reply_count": reply_count,
                "urls": urls,
            })

        return posts

    except Exception as e:
        logger.error(f"Failed to fetch posts from @{channel_username}: {e}")
        return []


async def ingest_channel(channel: TelegramChannel, db: AsyncSession) -> dict:
    """Fetch new posts from a channel and store them.

    Returns stats: {found, new, linked}.
    """
    stats = {"found": 0, "new": 0, "linked": 0}

    posts = await fetch_channel_posts(
        channel.username,
        limit=50,
        min_id=channel.last_message_id,
    )
    stats["found"] = len(posts)

    if not posts:
        return stats

    # Get all known article URLs for matching
    article_url_map = await _build_article_url_map(db)

    max_message_id = channel.last_message_id or 0

    for post_data in posts:
        max_message_id = max(max_message_id, post_data["message_id"])

        # Normalize and extract keywords
        text = normalize(post_data["text"]) if post_data["text"] else ""
        keywords = extract_keywords(text) if text else []

        # Check if any URL in the post matches a known article
        story_id = None
        shares_news_link = False
        for url in post_data["urls"]:
            normalized = normalize_url(url)
            if normalized in article_url_map:
                article = article_url_map[normalized]
                story_id = article.story_id
                shares_news_link = True
                break

        # Upsert the post
        stmt = (
            insert(TelegramPost)
            .values(
                channel_id=channel.id,
                message_id=post_data["message_id"],
                text=post_data["text"],
                date=post_data["date"],
                views=post_data["views"],
                forwards=post_data["forwards"],
                reply_count=post_data["reply_count"],
                urls=post_data["urls"],
                keywords=keywords,
                story_id=story_id,
                shares_news_link=shares_news_link,
                is_commentary=not shares_news_link and bool(text),
            )
            .on_conflict_do_nothing(constraint="uq_channel_message")
            .returning(TelegramPost.id)
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            stats["new"] += 1
            if story_id:
                stats["linked"] += 1

    # Update channel tracking
    channel.last_message_id = max_message_id
    channel.last_fetched_at = datetime.now(timezone.utc)

    await db.commit()
    logger.info(f"Ingested @{channel.username}: {stats}")
    return stats


async def ingest_all_channels(db: AsyncSession) -> dict:
    """Fetch posts from all active Telegram channels."""
    result = await db.execute(
        select(TelegramChannel).where(TelegramChannel.is_active.is_(True))
    )
    channels = result.scalars().all()

    total_stats = {"channels": len(channels), "found": 0, "new": 0, "linked": 0}

    for channel in channels:
        try:
            channel_stats = await ingest_channel(channel, db)
            total_stats["found"] += channel_stats["found"]
            total_stats["new"] += channel_stats["new"]
            total_stats["linked"] += channel_stats["linked"]
        except Exception as e:
            logger.error(f"Failed to ingest @{channel.username}: {e}")

    logger.info(f"Telegram ingestion complete: {total_stats}")
    return total_stats


async def link_unlinked_posts(db: AsyncSession) -> int:
    """Try to link posts that weren't linked during ingestion.

    Uses URL matching against articles added after the post was ingested.
    Returns count of newly linked posts.
    """
    # Get unlinked posts with URLs
    result = await db.execute(
        select(TelegramPost)
        .where(
            TelegramPost.story_id.is_(None),
            TelegramPost.shares_news_link.is_(False),
        )
        .limit(500)
    )
    posts = result.scalars().all()

    if not posts:
        return 0

    article_url_map = await _build_article_url_map(db)
    linked = 0

    for post in posts:
        for url in (post.urls or []):
            normalized = normalize_url(url)
            if normalized in article_url_map:
                article = article_url_map[normalized]
                post.story_id = article.story_id
                post.shares_news_link = True
                linked += 1
                break

    await db.commit()
    logger.info(f"Linked {linked} previously unlinked posts")
    return linked


async def compute_story_social_sentiment(story_id, db: AsyncSession) -> dict | None:
    """Compute aggregated social sentiment for a story.

    Creates a SocialSentimentSnapshot with current metrics.
    """
    # Get all posts linked to this story
    result = await db.execute(
        select(TelegramPost)
        .options(selectinload(TelegramPost.channel))
        .where(TelegramPost.story_id == story_id)
    )
    posts = result.scalars().all()

    if not posts:
        return None

    total_views = sum(p.views or 0 for p in posts)
    total_forwards = sum(p.forwards or 0 for p in posts)
    unique_channels = len({p.channel_id for p in posts})

    # Sentiment counts (from pre-computed sentiment_score)
    positive = sum(1 for p in posts if p.sentiment_score and p.sentiment_score > 0.2)
    negative = sum(1 for p in posts if p.sentiment_score and p.sentiment_score < -0.2)
    neutral = len(posts) - positive - negative

    sentiments = [p.sentiment_score for p in posts if p.sentiment_score is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

    # Framing distribution across posts
    framing_dist: dict[str, int] = {}
    for post in posts:
        for label in (post.framing_labels or []):
            framing_dist[label] = framing_dist.get(label, 0) + 1

    snapshot = SocialSentimentSnapshot(
        story_id=story_id,
        total_posts=len(posts),
        total_views=total_views,
        total_forwards=total_forwards,
        unique_channels=unique_channels,
        avg_sentiment=avg_sentiment,
        positive_count=positive,
        negative_count=negative,
        neutral_count=neutral,
        framing_distribution=framing_dist,
    )
    db.add(snapshot)
    await db.commit()

    return {
        "total_posts": len(posts),
        "total_views": total_views,
        "total_forwards": total_forwards,
        "unique_channels": unique_channels,
        "avg_sentiment": avg_sentiment,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "framing_distribution": framing_dist,
    }


# ---------------------------------------------------------------------------
# Telegram-post → Article conversion
# ---------------------------------------------------------------------------

# Maps Telegram channel usernames to Source slugs.
# Only channels whose posts should become first-class articles are listed.
CHANNEL_SOURCE_MAP: dict[str, str] = {
    "bbcpersian": "bbc-persian",
    "Tasnimnews": "tasnim",
    "farsna": "fars-news",
    "khabaronline_ir": "khabar-online",
    "presstv": "press-tv",
    "radiofarda": "radio-farda",
    "radiozamaneh": "radio-zamaneh",
    "zeitoons": "zeitoons",
    "iranintl": "iran-international",
}

# Minimum text length (in characters) for a post to be worth converting.
_MIN_POST_LENGTH = 50


def _clean_post_text(text: str) -> str:
    """Strip markdown artefacts from a Telegram post for use as article text.

    * Replaces ``[label](url)`` with just ``label``
    * Removes bare URLs
    * Removes ``@channel`` / ``@username`` mentions
    """
    if not text:
        return ""
    # Markdown links → label only
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Bare URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # @mentions
    cleaned = re.sub(r"@\w+", "", cleaned)
    # Remove trailing source attribution like "| رادیو زمانه"
    cleaned = re.sub(r"\|\s*[^\n]+$", "", cleaned, flags=re.MULTILINE)
    # Collapse whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_title(cleaned_text: str, max_length: int = 100) -> str:
    """Derive a title from the cleaned post text.

    Uses the first sentence or first ``max_length`` characters, whichever
    is shorter.
    """
    if not cleaned_text:
        return ""
    # Try to grab the first line / sentence
    first_line = cleaned_text.split("\n")[0].strip()
    # If the first line is reasonably short, use it as-is
    if 0 < len(first_line) <= max_length:
        return first_line
    # Otherwise truncate at a word boundary
    truncated = first_line[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    return truncated + "…"


async def convert_telegram_posts_to_articles(db: AsyncSession) -> dict:
    """Convert Telegram posts into Article records so they enter the
    clustering / NLP / bias-scoring pipeline.

    Posts are matched to a Source via ``CHANNEL_SOURCE_MAP``.  Duplicate
    detection relies on the Article ``url`` unique constraint (constructed
    as ``https://t.me/{username}/{message_id}``).

    Returns ``{"checked": int, "created": int, "skipped_no_source": int,
               "skipped_short": int, "skipped_duplicate": int}``.
    """
    stats = {
        "checked": 0,
        "created": 0,
        "skipped_no_source": 0,
        "skipped_short": 0,
        "skipped_duplicate": 0,
    }

    # --- Pre-load source lookup (slug → Source) ---
    source_result = await db.execute(select(Source))
    sources_by_slug: dict[str, Source] = {
        s.slug: s for s in source_result.scalars().all()
    }

    # --- Pre-load channels (id → TelegramChannel) ---
    channel_result = await db.execute(select(TelegramChannel))
    channels_by_id: dict[uuid.UUID, TelegramChannel] = {
        c.id: c for c in channel_result.scalars().all()
    }

    # --- Get all posts; we'll filter out already-converted ones via URL ---
    posts_result = await db.execute(
        select(TelegramPost).order_by(TelegramPost.date.asc())
    )
    posts = posts_result.scalars().all()

    for post in posts:
        stats["checked"] += 1

        # Resolve channel username
        channel = channels_by_id.get(post.channel_id)
        if channel is None:
            stats["skipped_no_source"] += 1
            continue

        # Must have enough text
        raw_text = post.text or ""
        if len(raw_text) < _MIN_POST_LENGTH:
            stats["skipped_short"] += 1
            continue

        # Map channel → source
        source_slug = CHANNEL_SOURCE_MAP.get(channel.username)
        if source_slug is None:
            stats["skipped_no_source"] += 1
            continue
        source = sources_by_slug.get(source_slug)
        if source is None:
            stats["skipped_no_source"] += 1
            continue

        # Build article fields
        cleaned = _clean_post_text(raw_text)
        title = _extract_title(cleaned)
        if not title:
            stats["skipped_short"] += 1
            continue

        article_url = f"https://t.me/{channel.username}/{post.message_id}"
        summary = cleaned[:200] if cleaned else None

        stmt = (
            insert(Article)
            .values(
                source_id=source.id,
                title_original=title,
                title_fa=title,
                url=article_url,
                content_text=cleaned,
                summary=summary,
                language=channel.language or "fa",
                published_at=post.date,
            )
            .on_conflict_do_nothing(index_elements=["url"])
            .returning(Article.id)
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            stats["created"] += 1
        else:
            stats["skipped_duplicate"] += 1

    await db.commit()
    logger.info(f"Telegram → Article conversion: {stats}")
    return stats


async def _build_article_url_map(db: AsyncSession) -> dict:
    """Build a map of normalized URL -> Article for matching."""
    result = await db.execute(
        select(Article).where(Article.story_id.isnot(None))
    )
    articles = result.scalars().all()

    url_map = {}
    for article in articles:
        normalized = normalize_url(article.url)
        url_map[normalized] = article

    return url_map

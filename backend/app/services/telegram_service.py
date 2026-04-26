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
    """Get or create the Telethon client.

    Prefers a serialized session from settings.telegram_session_string (used on
    Railway where filesystem is ephemeral). Falls back to the local
    doornegar_session.session file for dev.
    """
    global _client
    if _client is not None and _client.is_connected():
        return _client

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if settings.telegram_session_string:
            logger.info("Using TELEGRAM_SESSION_STRING session")
            session = StringSession(settings.telegram_session_string)
        else:
            logger.info("Using file-based session (doornegar_session.session)")
            session = "doornegar_session"

        _client = TelegramClient(
            session,
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

        # Run the display cleaner once at ingest so the stored body is
        # already free of decorative emojis, **bold** markers, leading
        # bullets, channel-attribution tails. The Telegram analysis LLM
        # and homepage rendering then see a uniform plain-text payload.
        clean_text = clean_post_for_display(post_data["text"]) if post_data["text"] else ""
        # Keyword extraction runs on normalized cleaned text.
        text = normalize(clean_text) if clean_text else ""
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
                text=clean_text,
                date=post_data["date"],
                views=post_data["views"],
                forwards=post_data["forwards"],
                reply_count=post_data["reply_count"],
                urls=post_data["urls"],
                keywords=keywords,
                story_id=story_id,
                shares_news_link=shares_news_link,
                is_commentary=(
                    not shares_news_link
                    and is_discussion_post(clean_text, post_data["urls"])
                ),
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
    "iranintl_fa": "iran-international",
    # New channels from media ecosystem map
    "irnews": "irna",
    "isna94": "isna",
    "iribnews": "irib",
    "SharghDaily": "shargh",
    "EtemadOnline": "etemad",
    "hammihanonline": "hammihan",
    "mashreghnews_channel": "mashregh",
}

# Minimum text length (in characters) for a post to be worth converting.
_MIN_POST_LENGTH = 50


_URL_RE = re.compile(r"https?://[^\s<>\"'`]+")


def _extract_post_urls(text: str) -> list[str]:
    """Pull bare URLs out of a Telegram post body.

    Used by D2 to detect "outlet re-broadcasts its own RSS link to
    Telegram" — when the post text quotes the canonical article URL,
    creating a parallel t.me Article would be a guaranteed duplicate.

    Strips trailing punctuation (Persian/English) so a sentence-ending
    `.` or `،` doesn't break the URL match. Caps at 5 URLs to avoid
    pathological cases on link-spam posts.
    """
    if not text:
        return []
    raw = _URL_RE.findall(text)
    cleaned: list[str] = []
    for u in raw:
        # Drop common trailing punctuation that's not part of a URL.
        u = u.rstrip(".,;:!؟،؛»)>]")
        # Skip our own t.me / aggregator domains — only outbound links.
        low = u.lower()
        if any(d in low for d in ("t.me/", "telegram.me/", "telegram.org/")):
            continue
        cleaned.append(u)
        if len(cleaned) >= 5:
            break
    return cleaned


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


# Decorative leading markers that telegram channels prepend for visual flair —
# arrows, megaphones, bullets, video-icons. These always appear at line start
# in Iranian-news channels; stripping them keeps the rendered text uniform.
_TG_DECORATIVE_LEADS = (
    "\U0001F53B",  # 🔻 down arrow (negative)
    "\U0001F53A",  # 🔺 up arrow (positive)
    "\U0001F538",  # 🔸 small orange diamond
    "\U0001F539",  # 🔹 small blue diamond
    "\U0001F4E2",  # 📢 loudspeaker
    "\U0001F4FB",  # 📻 radio
    "\U0001F3A5",  # 🎥 movie camera
    "\u25B6",      # ▶ play
    "\u26A0",      # ⚠ warning
    "\U0001F525",  # 🔥 fire
    "\u2B50",      # ⭐ star
    "\U0001F4CC",  # 📌 pin
    "\U0001F517",  # 🔗 link
    "\U0001F551",  # 🕑 clock
)


_TG_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_TG_BULLET_RE = re.compile(r"^[\s\u202B\u202C]*[•·▪◾◼·]\s*", re.MULTILINE)
_TG_LEAD_DECOR_RE = re.compile(
    r"^[\s\u202B\u202C]*[" + "".join(re.escape(c) for c in _TG_DECORATIVE_LEADS) + r"]+[\s\u202B\u202C]*",
    re.MULTILINE,
)
# Trailing channel attribution like "│ کانال آخرین خبر" / "@channelname".
_TG_CHANNEL_TAIL_RE = re.compile(r"[│|]\s*(کانال|@)\s*[^\n│|]+\s*$", re.MULTILINE)


def clean_post_for_display(text: str | None) -> str:
    """Aggressive cleaner used at API response time and ingest persistence.

    Goal: render a uniform, plain-text post body — drop emoji decorations,
    markdown bold, leading bullets, channel-attribution tails. The frontend
    then doesn't have to reason about per-channel formatting flavors.

    Composes on top of `_clean_post_text` (URL/@-mention/markdown-link strip)
    for reuse.
    """
    if not text:
        return ""
    out = _clean_post_text(text)
    # Strip **bold** wrappers (keep inner)
    out = _TG_BOLD_RE.sub(r"\1", out)
    # Strip leading decorative emoji per line
    out = _TG_LEAD_DECOR_RE.sub("", out)
    # Strip leading bullets per line
    out = _TG_BULLET_RE.sub("", out)
    # Trailing channel attribution
    out = _TG_CHANNEL_TAIL_RE.sub("", out)
    # Re-collapse whitespace after the strips
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def is_discussion_post(text: str | None, urls: list[str] | None = None) -> bool:
    """Heuristic gate for "this post is analysis/discussion, not a headline."

    Drops:
      * Empty/null text
      * Posts whose cleaned body is shorter than 120 chars (likely a one-line
        news headline or quote)
      * Posts that are >70% URL by character count (link-spam reposts)
      * Posts that are a single line under 100 chars (headlines)

    Conservative — keeps anything that looks like analytical commentary even
    if short. Used by the story page to filter the post list before rendering.
    """
    if not text or not text.strip():
        return False
    cleaned = clean_post_for_display(text)
    if len(cleaned) < 120:
        return False
    # Single-line short posts are typically headlines.
    lines = [ln for ln in cleaned.split("\n") if ln.strip()]
    if len(lines) == 1 and len(cleaned) < 200:
        return False
    if urls:
        url_chars = sum(len(u) for u in urls)
        # If after cleaning the URLs are gone but the original was URL-heavy,
        # it was a link-card post.
        if url_chars > 0 and len(text) > 0 and url_chars / len(text) > 0.4:
            return False
    return True


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

        # Skip aggregator channels — their posts are processed for links,
        # not converted into articles themselves.
        if getattr(channel, "is_aggregator", False) or channel.username in AGGREGATOR_USERNAMES:
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
        # Respect the RSS source's is_active flag here too. Without this
        # gate, Telegram mirror posts keep creating Article rows against
        # an outlet that was deliberately disabled — which makes fetch-
        # stats say "inactive" with 60+ articles today. Inactive means
        # inactive across all ingest paths.
        if not source.is_active:
            stats["skipped_no_source"] += 1
            continue

        # D2 — Telegram-cites-RSS suppression. If the post text links
        # to an article URL we already have ingested (typical pattern:
        # outlets re-broadcast their own RSS articles to Telegram with
        # the canonical link in the body), don't create a parallel
        # Telegram Article. The TelegramPost row is preserved for
        # social-signal aggregation. This eliminates the most common
        # source of t.me-vs-RSS duplicates from the same outlet.
        post_urls = _extract_post_urls(raw_text)
        if post_urls:
            existing = await db.execute(
                select(Article.id).where(Article.url.in_(post_urls)).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                stats.setdefault("skipped_cites_rss", 0)
                stats["skipped_cites_rss"] += 1
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


# ---------------------------------------------------------------------------
# Aggregator channel link extraction
# ---------------------------------------------------------------------------

# Telegram channel usernames that are aggregators (share links, not original content).
# Posts from these channels are mined for article URLs instead of being
# converted into articles themselves.
AGGREGATOR_USERNAMES: set[str] = {
    "akhbarefori",
    "akaborz",
    "VahidOnline",
    "mamlekate",
}

# Domains to skip when extracting links from aggregator posts.
_SKIP_DOMAINS: set[str] = {
    "t.me",
    "telegram.me",
    "telegram.org",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "linkedin.com",
    "aparat.com",
}


def _is_news_link(url: str) -> bool:
    """Return True if the URL looks like a news article (not social media / Telegram)."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().replace("www.", "")
        if not hostname:
            return False
        # Skip social media and Telegram links
        for skip in _SKIP_DOMAINS:
            if hostname == skip or hostname.endswith(f".{skip}"):
                return False
        # Must have a path beyond just "/" to look like an article
        path = parsed.path.rstrip("/")
        if not path or path == "":
            return False
        return True
    except Exception:
        return False


def _domain_from_url(url: str) -> str:
    """Extract the base domain from a URL (without www.)."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().replace("www.", "")
        return hostname
    except Exception:
        return ""


def _build_domain_to_source_slug() -> dict[str, str]:
    """Build a static mapping from known news domains to source slugs.

    Uses the website_url from INITIAL_SOURCES in the seed data.
    We hard-code it here so the function works without a DB call and stays
    fast. Update this when new sources are added.
    """
    return {
        # Diaspora / international
        "bbc.com": "bbc-persian",
        "bbc.co.uk": "bbc-persian",
        "iranintl.com": "iran-international",
        "iranwire.com": "iranwire",
        "radiozamaneh.com": "radio-zamaneh",
        "dw.com": "dw-persian",
        "rfi.fr": "rfi-farsi",
        "radiofarda.com": "radio-farda",
        "ir.voanews.com": "voa-farsi",
        "fa.euronews.com": "euronews-persian",
        "kayhan.london": "kayhan-london",
        "zeitoons.com": "zeitoons",
        # State / semi-state
        "tasnimnews.com": "tasnim",
        "presstv.ir": "press-tv",
        "mehrnews.com": "mehr-news",
        "isna.ir": "isna",
        "farsnews.ir": "fars-news",
        "tabnak.ir": "tabnak",
        "khabaronline.ir": "khabar-online",
        # Additional common domains seen in the CHANNEL_SOURCE_MAP outlets
        "irna.ir": "irna",
        "iribnews.ir": "irib",
        "mashreghnews.ir": "mashregh",
        "sharghDaily.ir": "shargh",
        "etemadnewspaper.ir": "etemad",
        "hammihan.com": "hammihan",
    }


_DOMAIN_TO_SLUG = _build_domain_to_source_slug()


def _match_domain_to_slug(url: str) -> str | None:
    """Try to match a URL's domain to a known source slug.

    Checks exact domain first, then tries parent domain (e.g.
    ``fa.euronews.com`` matches ``fa.euronews.com`` directly, but
    ``news.isna.ir`` would match ``isna.ir`` via suffix).
    """
    domain = _domain_from_url(url)
    if not domain:
        return None
    # Exact match
    if domain in _DOMAIN_TO_SLUG:
        return _DOMAIN_TO_SLUG[domain]
    # Try parent domain (strip first subdomain)
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[1:])
        if parent in _DOMAIN_TO_SLUG:
            return _DOMAIN_TO_SLUG[parent]
    return None


async def _fetch_page_metadata(url: str) -> dict | None:
    """Fetch a page and extract title, description, image, and publish date.

    Uses httpx + trafilatura for content extraction and regex for OG tags.
    Returns None if the page cannot be fetched.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Doornegar/0.1)",
                "Accept-Language": "fa,en;q=0.9",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        metadata: dict = {"url": str(response.url)}  # follow redirects

        # Extract og:title
        og_title = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
            html, re.IGNORECASE,
        )
        if og_title:
            metadata["title"] = og_title.group(1).strip()
        else:
            # Fallback to <title> tag
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            if title_match:
                metadata["title"] = title_match.group(1).strip()

        # Extract og:description
        og_desc = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            html, re.IGNORECASE,
        )
        if og_desc:
            metadata["description"] = og_desc.group(1).strip()

        # Extract og:image
        og_image = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html, re.IGNORECASE,
        )
        if og_image:
            metadata["image_url"] = og_image.group(1).strip()

        # Try to extract publish date from og/meta tags
        for date_prop in (
            "article:published_time",
            "og:article:published_time",
            "datePublished",
            "publish_date",
        ):
            date_match = re.search(
                rf'<meta[^>]+(?:property|name)=["\'](?:{re.escape(date_prop)})["\'][^>]+content=["\']([^"\']+)["\']',
                html, re.IGNORECASE,
            )
            if date_match:
                try:
                    from dateutil.parser import parse as parse_date
                    metadata["published_at"] = parse_date(date_match.group(1))
                except Exception:
                    pass
                break

        # Extract article text via trafilatura (optional, best-effort)
        try:
            from trafilatura import extract as traf_extract
            content = traf_extract(html, include_comments=False, include_tables=False)
            if content and len(content) > 50:
                metadata["content_text"] = content
        except Exception:
            pass

        return metadata if metadata.get("title") else None

    except Exception as e:
        logger.debug(f"Failed to fetch metadata from {url}: {e}")
        return None


async def extract_articles_from_aggregators(db: AsyncSession) -> dict:
    """Process posts from aggregator channels and create Article records
    for the news links they contain.

    For each aggregator channel:
    1. Get recent posts (already ingested by ingest_all_channels)
    2. Extract non-social-media URLs from each post
    3. Skip URLs we already have as articles
    4. Fetch the page and extract metadata (title, og:image, etc.)
    5. Create an Article record linked to the matching source

    Returns stats dict with counts.
    """
    stats = {
        "posts_checked": 0,
        "links_found": 0,
        "links_skipped_social": 0,
        "links_already_known": 0,
        "links_no_source_match": 0,
        "links_fetch_failed": 0,
        "articles_created": 0,
    }

    # Get aggregator channels
    result = await db.execute(
        select(TelegramChannel).where(
            TelegramChannel.is_active.is_(True),
            TelegramChannel.is_aggregator.is_(True),
        )
    )
    aggregator_channels = result.scalars().all()

    if not aggregator_channels:
        # Fallback: identify aggregators by username
        result = await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.username.in_(AGGREGATOR_USERNAMES),
            )
        )
        aggregator_channels = result.scalars().all()

    if not aggregator_channels:
        logger.info("No aggregator channels found — skipping link extraction")
        return stats

    channel_ids = [ch.id for ch in aggregator_channels]
    channel_names = {ch.id: ch.username for ch in aggregator_channels}

    # Get posts from aggregator channels that haven't been fully processed.
    # We look at posts from the last 3 days to avoid re-processing very old posts.
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    posts_result = await db.execute(
        select(TelegramPost)
        .where(
            TelegramPost.channel_id.in_(channel_ids),
            TelegramPost.date >= cutoff,
        )
        .order_by(TelegramPost.date.desc())
    )
    posts = posts_result.scalars().all()

    # Pre-load existing article URLs for duplicate checking
    existing_urls_result = await db.execute(select(Article.url))
    existing_urls: set[str] = {row[0] for row in existing_urls_result.all()}

    # Pre-load sources by slug
    source_result = await db.execute(select(Source))
    sources_by_slug: dict[str, Source] = {
        s.slug: s for s in source_result.scalars().all()
    }

    for post in posts:
        stats["posts_checked"] += 1
        urls = post.urls or []

        for url in urls:
            stats["links_found"] += 1

            # Filter out social media links
            if not _is_news_link(url):
                stats["links_skipped_social"] += 1
                continue

            # Check if we already have this URL
            if url in existing_urls:
                stats["links_already_known"] += 1
                continue

            # Try to match domain to a source
            source_slug = _match_domain_to_slug(url)
            if not source_slug or source_slug not in sources_by_slug:
                stats["links_no_source_match"] += 1
                continue

            source = sources_by_slug[source_slug]
            # Same is_active gate as the Telegram→Article mirror above.
            # Don't backfill articles against outlets marked inactive.
            if not source.is_active:
                stats["links_no_source_match"] += 1
                continue

            # Fetch the page metadata
            metadata = await _fetch_page_metadata(url)
            if not metadata or not metadata.get("title"):
                stats["links_fetch_failed"] += 1
                continue

            # Determine the canonical URL (may differ after redirects)
            canonical_url = metadata.get("url", url)
            if canonical_url in existing_urls:
                stats["links_already_known"] += 1
                continue

            # Detect language from title
            from app.services.ingestion import detect_language
            title = metadata["title"]
            language = detect_language(title)

            # Create the article
            stmt = (
                insert(Article)
                .values(
                    source_id=source.id,
                    title_original=title,
                    title_fa=title if language == "fa" else None,
                    url=canonical_url,
                    summary=metadata.get("description"),
                    image_url=metadata.get("image_url"),
                    content_text=metadata.get("content_text"),
                    language=language,
                    published_at=metadata.get("published_at"),
                )
                .on_conflict_do_nothing(index_elements=["url"])
                .returning(Article.id)
            )
            result = await db.execute(stmt)
            if result.scalar_one_or_none() is not None:
                stats["articles_created"] += 1
                existing_urls.add(canonical_url)  # prevent re-processing in this batch
                logger.info(
                    f"Created article from aggregator @{channel_names.get(post.channel_id, '?')}: "
                    f"{title[:60]} ({source_slug})"
                )

    await db.commit()
    logger.info(f"Aggregator link extraction complete: {stats}")
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

"""NLP processing pipeline.

Processes newly ingested articles through:
1. Text normalization (Persian)
2. Content extraction (if not already done)
3. Language detection
4. Keyword extraction
5. Embedding generation
6. Translation of titles (FA↔EN)

This runs as a batch job on articles that haven't been processed yet.
"""

import logging
from datetime import datetime, timezone

import httpx
from langdetect import detect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from trafilatura import extract

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.nlp.embeddings import generate_embeddings_batch
from app.nlp.persian import extract_keywords, extract_text_for_embedding, normalize
from app.services.translation import translate_batch_fa_to_en, translate_en_to_fa

logger = logging.getLogger(__name__)


async def process_unprocessed_articles(db: AsyncSession, batch_size: int = 50) -> dict:
    """Process articles that haven't been through the NLP pipeline yet.

    Returns stats: {processed, failed, skipped}.
    """
    # Gate: only articles whose content_type is in the source's
    # allowed whitelist reach NLP. Unclassified rows (content_type
    # IS NULL) wait for the next classifier pass; non-news labels
    # never reach the embedder, saving the bulk of the work.
    result = await db.execute(
        select(Article)
        .join(Source, Source.id == Article.source_id)
        .options(selectinload(Article.source))
        .where(
            Article.processed_at.is_(None),
            Article.content_type.isnot(None),
            text("(sources.content_filters -> 'allowed') @> to_jsonb(articles.content_type)"),
        )
        .order_by(Article.ingested_at.desc())
        .limit(batch_size)
    )
    articles = list(result.scalars().all())

    if not articles:
        return {"processed": 0, "failed": 0, "skipped": 0}

    logger.info(f"Processing {len(articles)} articles through NLP pipeline")
    stats = {"processed": 0, "failed": 0, "skipped": 0}

    # Step 1: Extract full content for articles that only have summaries
    for article in articles:
        if not article.content_text and article.url:
            try:
                content = await _fetch_and_extract(article.url)
                if content:
                    article.content_text = content
            except Exception as e:
                logger.warning(f"Content extraction failed for {article.url}: {e}")

    # Step 1b: Fetch og:image for articles missing images
    for article in articles:
        if not article.image_url and article.url:
            try:
                article.image_url = await _fetch_og_image(article.url)
            except Exception as e:
                logger.debug(f"og:image fetch failed for {article.url}: {e}")

    # Step 1c: Validate existing image URLs and fix broken ones
    for article in articles:
        if article.image_url:
            valid = await _validate_image_url(article.image_url)
            if not valid:
                logger.info(f"Broken image URL for article {article.id}, searching free alternative")
                article.image_url = None  # Clear broken URL

    # Step 1d: Search free images for articles still missing images
    for article in articles:
        if not article.image_url:
            try:
                query = article.title_original or article.title_fa or ""
                article.image_url = await _search_free_image(query)
            except Exception as e:
                logger.debug(f"Free image search failed: {e}")

    # Step 2: Normalize text and extract keywords
    for article in articles:
        try:
            text = article.content_text or article.summary or ""
            if not text and not article.title_original:
                stats["skipped"] += 1
                continue

            # Normalize title
            article.title_original = normalize(article.title_original)

            # Detect language if not set properly
            if text:
                try:
                    detected = detect(text[:500])
                    article.language = "fa" if detected in ("fa", "ar") else detected
                except Exception:
                    pass

            # Extract keywords
            article.keywords = extract_keywords(text)

        except Exception as e:
            logger.error(f"Text processing failed for article {article.id}: {e}")

    # Step 3: Generate embeddings in batch
    try:
        texts_for_embedding = []
        embeddable_articles = []
        for article in articles:
            # Pass the source slug so source-specific boilerplate
            # (scrape placeholders, recurring image captions, comments-
            # section chrome) gets stripped before the body feeds the
            # embedder. Cheap; avoids the cosine-poisoning we observed
            # in the 2026-04-26 embedder comparison.
            source_slug = article.source.slug if article.source else None
            text = extract_text_for_embedding(
                article.title_original,
                article.content_text or article.summary,
                source_slug=source_slug,
            )
            if text.strip():
                texts_for_embedding.append(text)
                embeddable_articles.append(article)

        if texts_for_embedding:
            # Offload the blocking OpenAI call (including retry sleeps)
            # to a thread so the event loop stays responsive.
            import asyncio as _asyncio
            embeddings = await _asyncio.to_thread(
                generate_embeddings_batch, texts_for_embedding
            )
            skipped = 0
            for article, embedding in zip(embeddable_articles, embeddings):
                # Treat None as "unknown" — leave any existing embedding
                # intact. Never overwrite with zero vectors: a zeroed
                # embedding silently breaks every cosine comparison
                # downstream, forcing the matcher to auto-reject and
                # pushing every article into cluster_new.
                if embedding is None:
                    skipped += 1
                    continue
                article.embedding = embedding
            if skipped:
                logger.warning(
                    f"Embedding: skipped {skipped}/{len(embeddings)} articles "
                    f"after retries — their embedding column was left unchanged"
                )

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")

    # Step 4: Translate titles
    try:
        fa_articles = [a for a in articles if a.language == "fa" and not a.title_en]
        en_articles = [a for a in articles if a.language == "en" and not a.title_fa]

        if fa_articles:
            fa_titles = [a.title_original for a in fa_articles]
            en_translations = translate_batch_fa_to_en(fa_titles)
            for article, translation in zip(fa_articles, en_translations):
                if translation:
                    article.title_en = translation
                    if not article.title_fa:
                        article.title_fa = article.title_original

        if en_articles:
            for article in en_articles:
                fa_translation = translate_en_to_fa(article.title_original)
                if fa_translation:
                    article.title_fa = fa_translation
                if not article.title_en:
                    article.title_en = article.title_original

    except Exception as e:
        logger.warning(f"Translation step failed (non-critical): {e}")

    # Step 4b: Use OpenAI to translate remaining English titles to Farsi
    try:
        still_en = [a for a in articles if a.language == "en" and not a.title_fa and a.title_original]
        if still_en and settings.openai_api_key:
            from openai import OpenAI
            from app.services.llm_helper import build_openai_params
            client = OpenAI(api_key=settings.openai_api_key)
            # Batch translate up to 30 at a time
            for batch_start in range(0, len(still_en), 30):
                batch = still_en[batch_start:batch_start + 30]
                titles = "\n".join(f"{i+1}. {a.title_original}" for i, a in enumerate(batch))
                params = build_openai_params(
                    model=settings.translation_model,
                    prompt=f"Translate these English news headlines to Farsi. Return ONLY the translations, one per line, numbered.\n\n{titles}",
                    max_tokens=2000,
                    temperature=0,
                )
                resp = client.chat.completions.create(**params)
                from app.services.llm_usage import log_llm_usage
                await log_llm_usage(
                    model=settings.translation_model,
                    purpose="translation.title",
                    usage=resp.usage,
                    meta={"batch_size": len(batch)},
                )
                lines = resp.choices[0].message.content.strip().split("\n")
                for i, article in enumerate(batch):
                    if i < len(lines):
                        # Remove numbering like "1. " or "۱. "
                        import re
                        translated = re.sub(r"^[\d۰-۹]+[\.\)]\s*", "", lines[i]).strip()
                        if translated:
                            article.title_fa = translated
                            logger.info(f"Translated: {article.title_original[:40]} -> {translated[:40]}")
    except Exception as e:
        logger.warning(f"OpenAI translation failed (non-critical): {e}")

    # Step 4c: Embedding-based dedup — kill near-duplicates before clustering
    # If a new article's embedding is > 0.92 similar to a recent article,
    # it's a repost/paraphrase. Detach it so it doesn't pollute clustering or bias.
    dedup_count = 0
    if embeddable_articles:
        from app.nlp.embeddings import cosine_similarity
        from datetime import timedelta
        cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)

        # Get recent articles with embeddings (potential duplicates of)
        recent_result = await db.execute(
            select(Article.id, Article.embedding)
            .where(
                Article.processed_at.isnot(None),
                Article.ingested_at >= cutoff_48h,
                Article.embedding.isnot(None),
            )
            .limit(500)
        )
        recent_pool = [(r[0], r[1]) for r in recent_result.all()]

        for article in embeddable_articles:
            if not article.embedding:
                continue
            for recent_id, recent_emb in recent_pool:
                if recent_id == article.id:
                    continue
                sim = cosine_similarity(article.embedding, recent_emb)
                if sim > 0.92:
                    # Near-duplicate — don't cluster this one
                    article.story_id = None  # ensure it stays unclustered
                    dedup_count += 1
                    logger.debug(f"  Embedding dedup: {(article.title_fa or article.title_original or '')[:40]} (sim={sim:.3f})")
                    break  # one match is enough

    stats["embedding_deduped"] = dedup_count

    # Step 5: Mark all as processed
    now = datetime.now(timezone.utc)
    for article in articles:
        article.processed_at = now
        stats["processed"] += 1

    await db.commit()
    logger.info(f"NLP pipeline complete: {stats}")
    return stats


async def _fetch_og_image(url: str) -> str | None:
    """Fetch a URL and extract the og:image meta tag, with fallbacks."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/0.1)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text[:50000], "html.parser")
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                return og["content"]
            # Fallback: twitter:image
            tw = soup.find("meta", attrs={"name": "twitter:image"})
            if tw and tw.get("content"):
                return tw["content"]
            # Fallback: find the first reasonably-sized <img> in the page
            img_url = _find_article_image(soup, url)
            if img_url:
                return img_url
    except Exception:
        pass
    return None


# Patterns that indicate an image is NOT an article image (icons, tracking, ads, logos)
_SKIP_IMG_PATTERNS = (
    "logo", "icon", "favicon", "avatar", "badge", "sprite",
    "pixel", "tracking", "analytics", "ads", "banner-ad",
    "widget", "button", "arrow", "spinner", "loading",
    "spacer", "blank", "transparent", "1x1", "gravatar",
    "emoji", "smiley", "share", "social", "facebook", "twitter",
    "telegram", "whatsapp", "pinterest", "rss",
)

# File extensions that are unlikely to be article images
_SKIP_IMG_EXTENSIONS = (".svg", ".gif", ".ico", ".webp")


def _find_article_image(soup, base_url: str) -> str | None:
    """Find the first likely article image from <img> tags in the HTML.

    Skips tiny icons, tracking pixels, ads, and logos by checking:
    - explicit width/height attributes (skip if < 150px)
    - URL patterns that indicate non-article images
    - common icon/logo class names
    """
    from urllib.parse import urljoin

    for img in soup.find_all("img", limit=30):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        src = src.strip()
        if not src or src.startswith("data:"):
            continue

        src_lower = src.lower()

        # Skip tiny/known non-article images by URL pattern
        if any(pattern in src_lower for pattern in _SKIP_IMG_PATTERNS):
            continue

        # Skip unlikely file extensions
        if any(src_lower.endswith(ext) for ext in _SKIP_IMG_EXTENSIONS):
            continue

        # Check explicit width/height attributes — skip small images
        width = _parse_dimension(img.get("width"))
        height = _parse_dimension(img.get("height"))
        if width is not None and width < 150:
            continue
        if height is not None and height < 150:
            continue

        # Check CSS classes and id for icon/logo patterns
        classes = " ".join(img.get("class", [])).lower()
        img_id = (img.get("id") or "").lower()
        if any(p in classes or p in img_id for p in ("logo", "icon", "avatar", "badge", "sprite")):
            continue

        # Build absolute URL
        full_url = urljoin(base_url, src)

        # Basic sanity: must be http(s)
        if full_url.startswith(("http://", "https://")):
            return full_url

    return None


def _parse_dimension(value) -> int | None:
    """Parse a width/height attribute value to an integer, or None."""
    if value is None:
        return None
    try:
        # Handle values like "300", "300px", "100%"
        cleaned = str(value).strip().rstrip("px").rstrip("%")
        if "%" in str(value):
            return None  # percentage — can't determine absolute size
        return int(cleaned)
    except (ValueError, TypeError):
        return None


async def _validate_image_url(url: str) -> bool:
    """Check if an image URL is accessible (returns 200)."""
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            response = await client.head(url)
            return response.status_code == 200
    except Exception:
        return False


async def _search_free_image(query: str) -> str | None:
    """Search Wikimedia Commons for a free-to-use image related to the query.

    Images from Wikimedia Commons are freely licensed (CC/public domain).
    """
    import re
    # Extract key terms (3+ chars, Persian or Latin)
    words = re.findall(r'[\u0600-\u06FF\w]{3,}', query)
    if not words:
        return None
    search_terms = " ".join(words[:4])

    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Doornegar/0.1 (media transparency platform)"},
        ) as client:
            response = await client.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": search_terms,
                    "gsrnamespace": "6",
                    "gsrlimit": "5",
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime",
                    "iiurlwidth": "800",
                },
            )
            if response.status_code != 200:
                return None
            data = response.json()
            pages = data.get("query", {}).get("pages", {})

            for page in pages.values():
                info = page.get("imageinfo", [{}])[0]
                mime = info.get("mime", "")
                width = info.get("width", 0)
                if mime.startswith("image/") and "svg" not in mime and width >= 300:
                    thumb = info.get("thumburl") or info.get("url")
                    if thumb:
                        return thumb
    except Exception:
        pass

    return None


async def _fetch_and_extract(url: str) -> str | None:
    """Fetch a URL and extract the main article text."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.ingestion_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/0.1)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return extract(response.text, include_comments=False, include_tables=False)
    except Exception:
        return None

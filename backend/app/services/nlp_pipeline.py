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
from sqlalchemy import select, text as sa_text
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

    Session lifecycle: this function does several minutes of HTTP fetches
    + LLM calls between the initial SELECT and the final write. Without
    intermediate commits, Neon's 5-min idle reaper kills the connection
    mid-run, surfacing as InterfaceError on the final commit and
    leaving 30%+ of articles with NULL embeddings (root cause of the
    "318/911 articles in last 24h have NULL embedding" dashboard issue
    on 2026-05-01). We now commit between phases — and inside the
    long Step 1 HTTP-fetch loop every 10 articles — so each commit
    works as a connection heartbeat AND saves partial work, making
    runs idempotent across container restarts.

    NULL-embedding retry (Parham 2026-05-03): articles whose embedding
    API call genuinely failed (rate limit / content policy / 5xx past
    the 5-attempt retry window) used to be permanently orphaned —
    `processed_at` was set even though `embedding` stayed NULL, so the
    `processed_at IS NULL` gate excluded them from every subsequent
    run. The 39.1% NULL rate canary on 2026-05-03 traced to this trap.
    Fix: also pull articles with `processed_at IS NOT NULL AND
    embedding IS NULL AND ingested_at >= NOW() - 14d` so they get
    re-embedded on subsequent maintenance runs. The 14d cap prevents
    digging into ancient data on first deploy.

    Backlog starvation fix (2026-07-16): the selection query used to
    `ORDER BY ingested_at DESC` with a flat 200-per-run cap (MAX_ITERS
    in step_process). Whenever a single run ingests more than 200
    newly-eligible articles — routine during high-volume news days —
    the oldest stragglers get bumped to the back on every subsequent
    run too, because DESC always hands the next run's fresh batch
    priority over last run's leftovers. Nothing ever promotes them
    back to the front, so they can silently age past the 7-day
    strict-retention cutoff (`step_delete_aged`) and get deleted
    having never been embedded or clustered — a real article quietly
    dropped from the pipeline, not just delayed. Fix: articles waiting
    more than 24h are selected first (oldest-first within that tier),
    then the remaining budget goes to fresh arrivals newest-first as
    before. 24h leaves 6 full days of margin before the retention
    cliff.
    """
    from datetime import timedelta as _td
    from sqlalchemy import or_ as _or, case as _case, func as _func
    retry_cutoff = datetime.now(timezone.utc) - _td(days=14)
    starvation_cutoff = datetime.now(timezone.utc) - _td(hours=24)
    # Single ORDER BY that sorts the >24h tier oldest-first (true FIFO —
    # relieves the most at-risk articles first) and the <24h tier
    # newest-first (freshness). Negating epoch within the fresh tier
    # lets one `.asc()` express both directions at once.
    _epoch = _func.extract("epoch", Article.ingested_at)
    _within_tier_order = _case(
        (Article.ingested_at < starvation_cutoff, _epoch),
        else_=-_epoch,
    )

    # Cycle-2 audit (2026-05-07): reset normalize-path counter at the
    # START as well as the END. The module-global counter accumulates
    # increments from non-NLP callers (telegram_service, admin
    # endpoints) between cron runs; resetting only at the end means
    # the next run's stats include that pollution. Reset both ends.
    try:
        from app.nlp.persian import (
            reset_normalize_path_counts as _reset_norm_paths_pre,
        )
        _reset_norm_paths_pre()
    except Exception:
        pass

    # Gate: only articles whose content_type is in the source's
    # allowed whitelist reach NLP. Unclassified rows (content_type
    # IS NULL) wait for the next classifier pass; non-news labels
    # never reach the embedder, saving the bulk of the work.
    # Defer 4 heavy JSONB cols (cycle-1 audit Island 2): this batch will
    # RECOMPUTE embedding/keywords/named_entities, so loading the prior
    # values is pure waste. content_text IS read at L196 for embedding
    # text, so keep it loaded. Saves ~300 KB per 50-article batch.
    from sqlalchemy.orm import defer as _defer_proc
    result = await db.execute(
        select(Article)
        .join(Source, Source.id == Article.source_id)
        .options(
            selectinload(Article.source),
            _defer_proc(Article.embedding),
            _defer_proc(Article.keywords),
            _defer_proc(Article.named_entities),
        )
        .where(
            _or(
                Article.processed_at.is_(None),
                # Stuck NULL-embedding retry — see docstring.
                (
                    Article.processed_at.isnot(None)
                    & Article.embedding.is_(None)
                    & (Article.ingested_at >= retry_cutoff)
                ),
            ),
            Article.content_type.isnot(None),
            sa_text("(sources.content_filters -> 'allowed') @> to_jsonb(articles.content_type)"),
        )
        .order_by(
            _case((Article.ingested_at < starvation_cutoff, 0), else_=1).asc(),
            _within_tier_order.asc(),
        )
        .limit(batch_size)
    )
    articles = list(result.scalars().all())

    if not articles:
        return {"processed": 0, "failed": 0, "skipped": 0}

    logger.info(f"Processing {len(articles)} articles through NLP pipeline")
    stats = {"processed": 0, "failed": 0, "skipped": 0}

    # Step 1: Extract full content for articles that only have summaries.
    # HTTP fetches with 10s timeouts can cumulatively exceed Neon's 5-min
    # idle reaper window on a 50-article batch — commit every 10 articles
    # as a heartbeat AND to persist partial work.
    for i, article in enumerate(articles):
        if not article.content_text and article.url:
            try:
                content = await _fetch_and_extract(article.url)
                if content:
                    article.content_text = content
            except Exception as e:
                logger.warning(f"Content extraction failed for {article.url}: {e}")
        if (i + 1) % 10 == 0:
            await db.commit()
    await db.commit()

    # Step 1b: Fetch og:image for articles missing images
    for i, article in enumerate(articles):
        if not article.image_url and article.url:
            try:
                article.image_url = await _fetch_og_image(article.url)
            except Exception as e:
                logger.debug(f"og:image fetch failed for {article.url}: {e}")
        if (i + 1) % 10 == 0:
            await db.commit()
    await db.commit()

    # Step 1c: Validate existing image URLs and fix broken ones
    for i, article in enumerate(articles):
        if article.image_url:
            valid = await _validate_image_url(article.image_url)
            if not valid:
                logger.info(f"Broken image URL for article {article.id}, searching free alternative")
                article.image_url = None  # Clear broken URL
        if (i + 1) % 10 == 0:
            await db.commit()
    await db.commit()

    # Step 1d: Search free images for articles still missing images
    for i, article in enumerate(articles):
        if not article.image_url:
            try:
                query = article.title_original or article.title_fa or ""
                article.image_url = await _search_free_image(query)
            except Exception as e:
                logger.debug(f"Free image search failed: {e}")
        if (i + 1) % 10 == 0:
            await db.commit()
    await db.commit()

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
            # Cycle-1 audit Island 2: count text-processing failures so
            # a regression in normalize / detect / extract_keywords
            # shows up in stats. Without this, the trap fires silently:
            # processed_at gets stamped at L383 because embed_ok=True
            # even though keywords/title_original may be unchanged.
            stats["text_processing_errors"] = stats.get("text_processing_errors", 0) + 1
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
            # Cost ledger entry (Parham 2026-05-03 audit): the embeddings
            # API was a $9/mo blind spot in the cost dashboard. We log
            # an estimate here — text-embedding-3-small is ~1 token per
            # 4 characters of Persian, $0.02/1M tokens. Best-effort:
            # actual usage info isn't returned by the batch helper, so
            # this is an upper-bound estimate that surfaces the pattern
            # of spend without complicating the embeddings module.
            try:
                from app.services.llm_usage import log_llm_usage
                from app.nlp.embeddings import EMBEDDING_MODEL as _EMB_MODEL
                # 1 token ~= 4 chars; cost = $0.02 per 1M tokens
                est_tokens = sum(len(t) for t in texts_for_embedding) // 4
                est_cost = est_tokens * 0.02 / 1_000_000
                class _UsageStub:
                    prompt_tokens = est_tokens
                    completion_tokens = 0
                    total_tokens = est_tokens
                    cached_tokens = 0
                await log_llm_usage(
                    model=_EMB_MODEL,
                    purpose="embedding.nlp_pipeline",
                    usage=_UsageStub(),
                    meta={
                        "batch_size": len(texts_for_embedding),
                        "estimated": True,
                        "estimated_cost_usd": round(est_cost, 6),
                    },
                )
            except Exception as _e:
                # Logging is best-effort; never fail the pipeline on it.
                logger.debug(f"Embedding cost log failed: {_e}")

            skipped = 0
            # Cycle-1 audit Island 2: per-source breakdown of embedding
            # skips so one source's NLP pipeline silently failing is
            # distinguishable from a blanket OpenAI outage.
            skipped_by_source: dict = {}
            for article, embedding in zip(embeddable_articles, embeddings):
                # Treat None as "unknown" — leave any existing embedding
                # intact. Never overwrite with zero vectors: a zeroed
                # embedding silently breaks every cosine comparison
                # downstream, forcing the matcher to auto-reject and
                # pushing every article into cluster_new.
                if embedding is None:
                    skipped += 1
                    src_key = (
                        getattr(article.source, "slug", None)
                        if hasattr(article, "source") and article.source
                        else "unknown"
                    )
                    skipped_by_source[src_key] = skipped_by_source.get(src_key, 0) + 1
                    continue
                article.embedding = embedding
            if skipped:
                logger.warning(
                    f"Embedding: skipped {skipped}/{len(embeddings)} articles "
                    f"after retries — their embedding column was left unchanged. "
                    f"By source: {skipped_by_source}"
                )
                stats["embedding_skipped_by_source"] = skipped_by_source

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")

    # Heartbeat after the multi-minute embedding phase.
    await db.commit()

    # Step 4: Translate titles
    try:
        fa_articles = [a for a in articles if a.language == "fa" and not a.title_en]
        en_articles = [a for a in articles if a.language == "en" and not a.title_fa]

        # Cycle-1 audit Island 2: track translation outcomes per-locale
        # so silent None returns (the April 2026 zero-vector pattern
        # shape) become visible in stats. Without per-article tracking,
        # a chronic Helsinki batch failure looks identical to "no FA
        # articles in batch" — invisible drift.
        if fa_articles:
            fa_titles = [a.title_original for a in fa_articles]
            en_translations = translate_batch_fa_to_en(fa_titles)
            fa_to_en_failed = 0
            for article, translation in zip(fa_articles, en_translations):
                if translation:
                    article.title_en = translation
                    if not article.title_fa:
                        article.title_fa = article.title_original
                else:
                    fa_to_en_failed += 1
                    logger.debug(
                        "translate_fa_to_en returned None for article "
                        "id=%s source=%s",
                        article.id,
                        getattr(article.source, "slug", None) if hasattr(article, "source") else None,
                    )
            stats["translation_fa_to_en_failed"] = fa_to_en_failed

        if en_articles:
            en_to_fa_failed = 0
            for article in en_articles:
                fa_translation = translate_en_to_fa(article.title_original)
                if fa_translation:
                    article.title_fa = fa_translation
                else:
                    en_to_fa_failed += 1
                if not article.title_en:
                    article.title_en = article.title_original
            stats["translation_en_to_fa_failed"] = en_to_fa_failed

    except Exception as e:
        logger.warning(f"Translation step failed (non-critical): {e}")

    # Heartbeat after Step 4 LLM-translation calls.
    await db.commit()

    # Step 4b: Use OpenAI to translate remaining English titles to Farsi
    try:
        still_en = [a for a in articles if a.language == "en" and not a.title_fa and a.title_original]
        if still_en and settings.openai_api_key:
            # Cycle-1 audit Island 2: AsyncOpenAI + await so the LLM
            # call doesn't block the event loop ~1-2s per batch.
            from openai import AsyncOpenAI
            from app.services.llm_helper import build_openai_params
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            # Batch translate using the hoisted setting. Cycle-2 audit
            # (2026-05-07): the slice was hard-coded to `+30` while the
            # range stride used the setting — raising the setting to 50
            # would have skipped articles 30-50 in every iteration; lowering
            # it to 20 would have processed 20-30 twice. Use the setting
            # for both sides.
            _batch_size = settings.nlp_translation_batch_size
            for batch_start in range(0, len(still_en), _batch_size):
                batch = still_en[batch_start:batch_start + _batch_size]
                titles = "\n".join(f"{i+1}. {a.title_original}" for i, a in enumerate(batch))
                params = build_openai_params(
                    model=settings.translation_model,
                    prompt=f"Translate these English news headlines to Farsi. Return ONLY the translations, one per line, numbered.\n\n{titles}",
                    max_tokens=2000,
                    temperature=0,
                )
                resp = await client.chat.completions.create(**params)
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

    # Heartbeat after Step 4b OpenAI-translation batch.
    await db.commit()

    # Step 4c: Embedding-based dedup — kill near-duplicates before clustering
    # If a new article's embedding is > 0.92 similar to a recent article,
    # it's a repost/paraphrase. Detach it so it doesn't pollute clustering or bias.
    dedup_count = 0
    if embeddable_articles:
        from app.nlp.embeddings import cosine_similarity
        from datetime import timedelta
        cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)

        # Get recent articles with embeddings (potential duplicates of)
        # Cycle-1 audit Island 2: dropped 500 → 100. Cycle-7 (2026-05-13):
        # dropped 100 → 30 after the maintenance test showed the dedup
        # pool being fetched on every batch in step_process's loop. At
        # ~4 KB per JSONB embedding × 100 articles × 10 batches per run,
        # this was ~4 MB per cron just for dedup. 30 still captures the
        # dense-window repost cases without the O(n²) tail.
        recent_result = await db.execute(
            select(Article.id, Article.embedding)
            .where(
                Article.processed_at.isnot(None),
                Article.ingested_at >= cutoff_48h,
                Article.embedding.isnot(None),
            )
            .order_by(Article.ingested_at.desc())
            .limit(30)
        )
        recent_pool = [(r[0], r[1]) for r in recent_result.all()]

        for article in embeddable_articles:
            if not article.embedding:
                continue
            for recent_id, recent_emb in recent_pool:
                if recent_id == article.id:
                    continue
                sim = cosine_similarity(article.embedding, recent_emb)
                if sim > settings.nlp_dedup_cosine_threshold:
                    # Near-duplicate — don't cluster this one
                    article.story_id = None  # ensure it stays unclustered
                    dedup_count += 1
                    logger.debug(f"  Embedding dedup: {(article.title_fa or article.title_original or '')[:40]} (sim={sim:.3f})")
                    break  # one match is enough

    stats["embedding_deduped"] = dedup_count

    # Step 5: Mark as processed — but ONLY if the work actually succeeded.
    # Sentinel column trap (Parham 2026-05-03): the prior code
    # unconditionally set `processed_at = now` even when embedding had
    # failed (returned None). The article kept `embedding IS NULL` but
    # `processed_at IS NOT NULL`, so the next run's `processed_at IS NULL`
    # gate excluded it forever. Result: 1097 permanently-orphaned articles
    # accumulated by 2026-05-03 and a 39% NULL-embedding rate.
    #
    # Fix: only stamp `processed_at` when the article either
    #   (a) has an embedding now (NLP succeeded), OR
    #   (b) has no source content for embedding to consume (so
    #       re-trying wouldn't help — leave it stamped to skip).
    # Articles that had content but failed to embed keep `processed_at
    # IS NULL` and are picked up on the next maintenance run. The
    # OR-clause in the gate (`embedding IS NULL AND processed_at IS NOT
    # NULL` retry) becomes a belt-and-suspenders for the legacy backlog.
    now = datetime.now(timezone.utc)
    skipped_unstamped = 0
    for article in articles:
        had_content_to_embed = bool(
            (article.content_text or article.summary or "").strip()
        )
        embed_ok = article.embedding is not None
        if embed_ok or not had_content_to_embed:
            article.processed_at = now
            stats["processed"] += 1
        else:
            skipped_unstamped += 1
    stats["skipped_unstamped"] = skipped_unstamped
    if skipped_unstamped:
        logger.warning(
            f"NLP: left {skipped_unstamped}/{len(articles)} articles unstamped "
            f"(processed_at NULL) so they'll retry next run — embedding failed "
            f"AND content was present"
        )

    await db.commit()
    # Cycle-1 audit Island 2: surface Persian normalize-path counts so
    # a fallback-only deploy (hazm missing) is visible in stats. Reset
    # counters so the next cron sees only its own work.
    try:
        from app.nlp.persian import (
            get_normalize_path_counts as _get_norm_paths,
            reset_normalize_path_counts as _reset_norm_paths,
        )
        norm_paths = _get_norm_paths()
        stats["normalize_paths"] = norm_paths
        if norm_paths.get("hazm", 0) == 0 and norm_paths.get("fallback", 0) > 0:
            logger.warning(
                "Persian normalize: 100%% fallback path used (hazm "
                "presumed missing). Embedding inputs may drift vs prior "
                "deploys with hazm available."
            )
        _reset_norm_paths()
    except Exception as e:
        logger.debug(f"normalize-path stats unavailable: {e}")
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

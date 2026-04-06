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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from trafilatura import extract

from app.config import settings
from app.models.article import Article
from app.nlp.embeddings import generate_embeddings_batch
from app.nlp.persian import extract_keywords, extract_text_for_embedding, normalize
from app.services.translation import translate_batch_fa_to_en, translate_en_to_fa

logger = logging.getLogger(__name__)


async def process_unprocessed_articles(db: AsyncSession, batch_size: int = 50) -> dict:
    """Process articles that haven't been through the NLP pipeline yet.

    Returns stats: {processed, failed, skipped}.
    """
    result = await db.execute(
        select(Article)
        .where(Article.processed_at.is_(None))
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
            text = extract_text_for_embedding(
                article.title_original,
                article.content_text or article.summary,
            )
            if text.strip():
                texts_for_embedding.append(text)
                embeddable_articles.append(article)

        if texts_for_embedding:
            embeddings = generate_embeddings_batch(texts_for_embedding)
            for article, embedding in zip(embeddable_articles, embeddings):
                article.embedding = embedding

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

    # Step 5: Mark all as processed
    now = datetime.now(timezone.utc)
    for article in articles:
        article.processed_at = now
        stats["processed"] += 1

    await db.commit()
    logger.info(f"NLP pipeline complete: {stats}")
    return stats


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

"""Management commands for Doornegar backend."""

import asyncio
import sys


async def seed():
    """Seed the database with initial sources and Telegram channels."""
    from app.database import async_session
    from app.services.seed import seed_sources
    from app.services.seed_telegram import seed_telegram_channels

    async with async_session() as db:
        count = await seed_sources(db)
        print(f"Seeded {count} news sources.")

        tg_count = await seed_telegram_channels(db)
        print(f"Seeded {tg_count} Telegram channels.")


async def ingest():
    """Run one ingestion cycle manually."""
    from app.database import async_session
    from app.services.ingestion import ingest_all_sources

    async with async_session() as db:
        stats = await ingest_all_sources(db)
        print(f"Ingestion stats: {stats}")


async def process():
    """Run NLP processing on unprocessed articles."""
    from app.database import async_session
    from app.services.nlp_pipeline import process_unprocessed_articles

    async with async_session() as db:
        stats = await process_unprocessed_articles(db)
        print(f"NLP processing stats: {stats}")


async def cluster():
    """Run story clustering."""
    from app.database import async_session
    from app.services.clustering import cluster_articles

    async with async_session() as db:
        stats = await cluster_articles(db)
        print(f"Clustering stats: {stats}")


async def score():
    """Run LLM bias scoring on unscored articles."""
    from app.database import async_session
    from app.services.bias_scoring import score_unscored_articles

    async with async_session() as db:
        stats = await score_unscored_articles(db)
        print(f"Bias scoring stats: {stats}")


async def telegram():
    """Fetch posts from tracked Telegram channels and convert to articles."""
    from app.database import async_session
    from app.services.telegram_service import (
        convert_telegram_posts_to_articles,
        ingest_all_channels,
    )

    async with async_session() as db:
        stats = await ingest_all_channels(db)
        print(f"Telegram ingestion stats: {stats}")

        print("Converting Telegram posts to articles...")
        convert_stats = await convert_telegram_posts_to_articles(db)
        print(f"Telegram → Article conversion: {convert_stats}")


async def pipeline():
    """Run the full pipeline: ingest → process → cluster → score → telegram."""
    from app.database import async_session
    from app.services.bias_scoring import score_unscored_articles
    from app.services.clustering import cluster_articles
    from app.services.ingestion import ingest_all_sources
    from app.services.nlp_pipeline import process_unprocessed_articles

    async with async_session() as db:
        print("Step 1/6: Ingesting RSS feeds...")
        stats = await ingest_all_sources(db)
        print(f"  → {stats}")

        print("Step 2/6: NLP processing...")
        stats = await process_unprocessed_articles(db)
        print(f"  → {stats}")

        print("Step 3/6: Clustering stories...")
        stats = await cluster_articles(db)
        print(f"  → {stats}")

        print("Step 4/6: Bias scoring...")
        stats = await score_unscored_articles(db)
        print(f"  → {stats}")

        print("Step 5/6: Telegram ingestion...")
        try:
            from app.services.telegram_service import ingest_all_channels
            stats = await ingest_all_channels(db)
            print(f"  → {stats}")
        except Exception as e:
            print(f"  → Skipped (Telegram not configured): {e}")

        print("Step 6/6: Converting Telegram posts to articles...")
        try:
            from app.services.telegram_service import convert_telegram_posts_to_articles
            stats = await convert_telegram_posts_to_articles(db)
            print(f"  → {stats}")
        except Exception as e:
            print(f"  → Skipped: {e}")

        print()
        print("Step 7/8: Downloading/fixing story images...")
        try:
            await fill_images()
        except Exception as e:
            print(f"  → Image fill failed: {e}")

        print()
        print("Step 8/8: Checking for stories without images...")
        try:
            await check_images()
        except Exception as e:
            print(f"  → Image check failed: {e}")

        print("Pipeline complete!")


async def summarize():
    """Pre-generate summaries and bias analysis for all stories."""
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
            .where(Story.summary_fa.is_(None))
            .order_by(Story.article_count.desc())
        )
        stories = list(result.scalars().all())
        print(f"Generating summaries for {len(stories)} stories...")

        success = 0
        for story in stories:
            articles_info = [
                {
                    "id": str(a.id),
                    "source_slug": a.source.slug if a.source else None,
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
                import json as _json
                story.summary_en = _json.dumps({
                    "state_summary_fa": analysis.get("state_summary_fa"),
                    "diaspora_summary_fa": analysis.get("diaspora_summary_fa"),
                    "independent_summary_fa": analysis.get("independent_summary_fa"),
                    "bias_explanation_fa": analysis.get("bias_explanation_fa"),
                    "scores": analysis.get("scores"),
                }, ensure_ascii=False)
                await db.commit()
                success += 1
                print(f"  ✓ {story.title_fa[:50]}")
            except Exception as e:
                print(f"  ✗ {story.title_fa[:50]}: {e}")

        print(f"Done: {success}/{len(stories)} summaries generated")


async def download_images():
    """Download all article images locally for reliable serving."""
    from app.database import async_session
    from app.services.image_downloader import download_all_article_images

    async with async_session() as db:
        stats = await download_all_article_images(db)
        print(f"Image download stats: {stats}")


async def migrate_images_to_r2():
    """Upload all locally-stored images to Cloudflare R2 and update DB URLs."""
    import mimetypes
    from pathlib import Path

    from sqlalchemy import select, update

    from app.config import settings
    from app.database import async_session
    from app.models.article import Article
    from app.services.image_downloader import (
        IMAGES_DIR,
        LOCAL_IMAGE_BASE,
        _upload_to_r2,
        _is_r2_configured,
    )

    if not _is_r2_configured():
        print("R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, etc. in .env")
        return

    print(f"Uploading local images to R2 bucket: {settings.r2_bucket_name}")

    async with async_session() as db:
        # Find all articles with local /images/ URLs
        result = await db.execute(
            select(Article).where(Article.image_url.like(f"{LOCAL_IMAGE_BASE}/%"))
        )
        articles = list(result.scalars().all())
        print(f"Found {len(articles)} articles with local image URLs")

        # Map local filename → new R2 URL (to avoid re-uploading duplicates)
        uploaded_cache: dict[str, str] = {}
        uploaded = 0
        failed = 0
        missing_files = 0

        for i, article in enumerate(articles, 1):
            if not article.image_url:
                continue
            filename = article.image_url.rsplit("/", 1)[-1]

            # Already uploaded to R2?
            if filename in uploaded_cache:
                article.image_url = uploaded_cache[filename]
                uploaded += 1
                continue

            filepath = IMAGES_DIR / filename
            if not filepath.exists():
                missing_files += 1
                article.image_url = None
                continue

            content = filepath.read_bytes()
            content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

            r2_url = await _upload_to_r2(filename, content, content_type)
            if r2_url:
                article.image_url = r2_url
                uploaded_cache[filename] = r2_url
                uploaded += 1
                if i % 25 == 0:
                    print(f"  Uploaded {i}/{len(articles)}...")
                    await db.commit()
            else:
                failed += 1

        await db.commit()
        print(f"\n✓ Uploaded: {uploaded}")
        print(f"✗ Failed: {failed}")
        print(f"? Missing local files: {missing_files}")


async def fill_images():
    """Find stories without images and try to backfill from OG tags / Telegram previews.
    Downloads fetched images to local storage so they don't expire.
    """
    import re
    import httpx
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.image_downloader import download_image, LOCAL_IMAGE_BASE

    async def fetch_og_image(url: str, client: httpx.AsyncClient) -> str | None:
        try:
            is_telegram = "t.me/" in url
            fetch_url = url + "?embed=1&mode=tme" if is_telegram and "?embed" not in url else url
            resp = await client.get(fetch_url, timeout=10, follow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            if resp.status_code != 200:
                return None
            html = resp.text

            # For Telegram embed pages: background-image CSS
            # Telegram URLs are very long (500+ chars), so we match up to the closing quote
            if is_telegram:
                match = re.search(
                    r"tgme_widget_message_photo_wrap[^>]*background-image:url\('(https://cdn[^']+)'",
                    html
                )
                if match:
                    return match.group(1)
                match = re.search(
                    r"tgme_widget_message_video_thumb[^>]*background-image:url\('(https://cdn[^']+)'",
                    html
                )
                if match:
                    return match.group(1)

            # Standard OG tags
            for pattern in [
                r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
                r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
                r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
            ]:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    img_url = match.group(1).strip()
                    if img_url and not any(p in img_url.lower() for p in ["logo", "icon", "favicon"]):
                        return img_url
            return None
        except Exception as e:
            return None

    async def is_image_alive(url: str, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.head(url, timeout=5, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"})
            return resp.status_code == 200
        except Exception:
            return False

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(Story.source_count >= 2)
        )
        all_stories = list(result.scalars().all())

        # Identify stories needing fix: no image OR image is not yet local
        async with httpx.AsyncClient() as client:
            print("Checking image health for all stories...")
            stories_to_fix = []
            for story in all_stories:
                valid_articles = [a for a in story.articles if a.image_url and a.image_url.strip()]
                if not valid_articles:
                    stories_to_fix.append(story)
                    continue
                # If the first (displayed) image is already local, it's stable
                first_img = valid_articles[0].image_url
                if first_img.startswith(LOCAL_IMAGE_BASE):
                    continue
                # Remote image: check if it's still alive
                alive = await is_image_alive(first_img, client)
                if not alive:
                    stories_to_fix.append(story)
                    continue
                # Alive but remote: download it for stability
                stories_to_fix.append(story)

            print(f"Found {len(stories_to_fix)} stories to fix/stabilize")

            if not stories_to_fix:
                return

            filled = 0
            for story in stories_to_fix:
                title = (story.title_fa or "")[:60]
                print(f"  → {title}")
                fixed_any = False

                # Try existing image_urls first (they might be alive — if so just download)
                for article in story.articles:
                    if article.image_url and not article.image_url.startswith(LOCAL_IMAGE_BASE):
                        local = await download_image(article.image_url)
                        if local:
                            article.image_url = local
                            print(f"    ✓ stored: {local.rsplit('/', 1)[-1]}")
                            fixed_any = True
                            break

                # If that failed, fetch fresh image via embed page and download
                if not fixed_any:
                    for article in story.articles:
                        if not article.url:
                            continue
                        fresh = await fetch_og_image(article.url, client)
                        if fresh:
                            local = await download_image(fresh)
                            if local:
                                article.image_url = local
                                print(f"    ✓ fetched+stored: {local.rsplit('/', 1)[-1]}")
                                fixed_any = True
                                break

                if fixed_any:
                    filled += 1
                else:
                    print(f"    ✗ no image found")
            await db.commit()

        print(f"\nFixed {filled}/{len(stories_to_fix)} stories")


async def seed_media_dimensions():
    """Load media_dimensions values from JSON seed file and apply to all sources."""
    import json
    from pathlib import Path
    from sqlalchemy import select

    from app.database import async_session
    from app.models.source import Source

    seed_path = Path(__file__).parent / "app" / "services" / "media_dimensions_seed.json"
    if not seed_path.exists():
        print(f"Seed file not found: {seed_path}")
        return

    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session() as db:
        result = await db.execute(select(Source))
        sources = {s.slug: s for s in result.scalars().all()}

        updated = 0
        missing = []
        for slug, dims in data.items():
            src = sources.get(slug)
            if src:
                src.media_dimensions = dims
                updated += 1
            else:
                missing.append(slug)

        await db.commit()
        print(f"Updated media_dimensions on {updated} sources")
        if missing:
            print(f"Missing sources (not in DB): {', '.join(missing)}")


async def check_images():
    """Find stories where no article has an image — alerts about missing images."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles))
            .where(Story.source_count >= 2)
            .order_by(Story.trending_score.desc())
        )
        stories = list(result.scalars().all())

        missing = []
        for story in stories:
            has_image = any(
                a.image_url and a.image_url.strip()
                for a in story.articles
            )
            if not has_image:
                missing.append(story)

        total = len(stories)
        missing_count = len(missing)
        pct = (missing_count / total * 100) if total > 0 else 0

        print(f"=== Image Check ===")
        print(f"  Total visible stories: {total}")
        print(f"  Missing images:        {missing_count} ({pct:.1f}%)")

        if missing:
            print()
            print("Stories without images (top 20 by trending score):")
            for story in missing[:20]:
                title = (story.title_fa or story.title_en or "")[:70]
                print(f"  • {title} ({story.source_count} رسانه · {story.article_count} مقاله)")

        return {"total": total, "missing": missing_count, "percentage": round(pct, 1)}


async def status():
    """Show current system status — source counts, article counts, etc."""
    from sqlalchemy import func, select

    from app.database import async_session
    from app.models.article import Article
    from app.models.bias_score import BiasScore
    from app.models.social import TelegramChannel, TelegramPost
    from app.models.source import Source
    from app.models.story import Story

    async with async_session() as db:
        sources = (await db.execute(select(func.count(Source.id)))).scalar()
        articles = (await db.execute(select(func.count(Article.id)))).scalar()
        processed = (await db.execute(
            select(func.count(Article.id)).where(Article.processed_at.isnot(None))
        )).scalar()
        stories = (await db.execute(select(func.count(Story.id)))).scalar()
        blindspots = (await db.execute(
            select(func.count(Story.id)).where(Story.is_blindspot.is_(True))
        )).scalar()
        scored = (await db.execute(select(func.count(BiasScore.id)))).scalar()
        tg_channels = (await db.execute(select(func.count(TelegramChannel.id)))).scalar()
        tg_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar()

        print("=== Doornegar System Status ===")
        print(f"  News sources:       {sources}")
        print(f"  Articles ingested:  {articles}")
        print(f"  Articles processed: {processed}")
        print(f"  Stories:            {stories}")
        print(f"  Blind spots:        {blindspots}")
        print(f"  Bias scores:        {scored}")
        print(f"  Telegram channels:  {tg_channels}")
        print(f"  Telegram posts:     {tg_posts}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python manage.py <command>")
        print()
        print("Commands:")
        print("  seed      - Seed database with news sources & Telegram channels")
        print("  ingest    - Fetch articles from RSS feeds")
        print("  process   - Run NLP pipeline (embeddings, keywords, translation)")
        print("  cluster   - Group articles into stories")
        print("  score     - Run LLM bias scoring")
        print("  telegram  - Fetch posts from Telegram channels")
        print("  pipeline  - Run the full pipeline (all of the above)")
        print("  check-images - Alert on stories without images")
        print("  status    - Show system status and counts")
        sys.exit(1)

    command = sys.argv[1]
    commands = {
        "seed": seed,
        "ingest": ingest,
        "process": process,
        "cluster": cluster,
        "score": score,
        "telegram": telegram,
        "pipeline": pipeline,
        "summarize": summarize,
        "download-images": download_images,
        "check-images": check_images,
        "fill-images": fill_images,
        "migrate-images-to-r2": migrate_images_to_r2,
        "seed-media-dimensions": seed_media_dimensions,
        "status": status,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    asyncio.run(commands[command]())

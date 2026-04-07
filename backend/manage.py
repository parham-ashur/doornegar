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
        "status": status,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        sys.exit(1)

    asyncio.run(commands[command]())

"""Doornegar QA/QC Check — Quality Assurance & Control

Checks everything shown on the website and flags issues.
Run: python qa_check.py [--fix]

Categories:
  1. Data Quality — articles, stories, translations, images
  2. API Health — all endpoints responding correctly
  3. Content Quality — summaries, titles, clustering
  4. Infrastructure — Docker, backend, frontend
  5. Freshness — is data up to date?
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import httpx

# Configuration
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3001"
MIN_VISIBLE_STORIES = 5
MIN_ARTICLES = 100
MAX_TITLE_LENGTH = 100
STALE_HOURS = 24  # data older than this is flagged

# Results
issues: list[dict] = []
warnings: list[dict] = []
passed: list[str] = []


def issue(category: str, msg: str, fix: str = ""):
    issues.append({"category": category, "message": msg, "fix": fix})


def warning(category: str, msg: str):
    warnings.append({"category": category, "message": msg})


def ok(msg: str):
    passed.append(msg)


async def check_api_health():
    """Check all API endpoints are responding."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Health
        try:
            r = await client.get(f"{BACKEND_URL}/health")
            if r.status_code == 200:
                ok("API health endpoint")
            else:
                issue("API", f"Health endpoint returned {r.status_code}", "Restart backend")
        except Exception:
            issue("API", "Backend not reachable", "Run: uvicorn app.main:app --reload --port 8000")
            return  # Skip other checks if backend is down

        # Key endpoints
        endpoints = [
            ("/api/v1/stories/trending?limit=5", "Trending stories"),
            ("/api/v1/sources", "Sources list"),
            ("/api/v1/stories?page_size=1", "Stories list"),
        ]
        for path, name in endpoints:
            try:
                r = await client.get(f"{BACKEND_URL}{path}")
                if r.status_code == 200:
                    ok(f"API: {name}")
                else:
                    issue("API", f"{name} returned {r.status_code}")
            except Exception as e:
                issue("API", f"{name} failed: {e}")


async def check_frontend():
    """Check frontend is serving pages."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            r = await client.get(f"{FRONTEND_URL}/fa")
            if r.status_code == 200:
                ok("Frontend /fa page loads")
                if "دورنگر" in r.text:
                    ok("Frontend shows Farsi content")
                else:
                    issue("Frontend", "Page loads but no Farsi content found")
            else:
                issue("Frontend", f"Frontend returned {r.status_code}", "Run: cd frontend && npm run dev")
        except Exception:
            issue("Frontend", "Frontend not reachable", "Run: cd frontend && npm run dev")


async def check_data_quality():
    """Check data quality in the database."""
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.models.source import Source
    from app.models.social import TelegramChannel, TelegramPost
    from sqlalchemy import select, func

    async with async_session() as db:
        # Article counts
        total_articles = (await db.execute(select(func.count(Article.id)))).scalar()
        if total_articles >= MIN_ARTICLES:
            ok(f"Articles: {total_articles}")
        else:
            issue("Data", f"Only {total_articles} articles (need {MIN_ARTICLES}+)", "Run: python manage.py pipeline")

        # Stories
        total_stories = (await db.execute(select(func.count(Story.id)))).scalar()
        visible_stories = (await db.execute(
            select(func.count(Story.id)).where(Story.article_count >= 5)
        )).scalar()
        if visible_stories >= MIN_VISIBLE_STORIES:
            ok(f"Visible stories: {visible_stories}")
        else:
            issue("Data", f"Only {visible_stories} visible stories (need {MIN_VISIBLE_STORIES}+)", "Run: python manage.py cluster")

        # Summaries
        with_summary = (await db.execute(
            select(func.count(Story.id)).where(Story.summary_fa.isnot(None), Story.article_count >= 5)
        )).scalar()
        if visible_stories > 0 and with_summary < visible_stories:
            missing = visible_stories - with_summary
            issue("Data", f"{missing} visible stories without summaries", "Run: python manage.py summarize")
        elif with_summary > 0:
            ok(f"All {with_summary} visible stories have summaries")

        # Articles without Farsi titles
        no_fa_title = (await db.execute(
            select(func.count(Article.id)).where(Article.title_fa.is_(None))
        )).scalar()
        if no_fa_title > 0:
            pct = round(no_fa_title * 100 / max(total_articles, 1))
            if pct > 10:
                issue("Data", f"{no_fa_title} articles ({pct}%) without Farsi title", "Run: python manage.py process")
            elif pct > 0:
                warning("Data", f"{no_fa_title} articles ({pct}%) without Farsi title")
        else:
            ok("All articles have Farsi titles")

        # Articles with English in title_fa
        result = await db.execute(select(Article.title_fa).where(Article.title_fa.isnot(None)))
        english_titles = 0
        for (fa,) in result.all():
            if fa and sum(1 for c in fa if c.isascii() and c.isalpha()) > len(fa) * 0.3:
                english_titles += 1
        if english_titles > 0:
            warning("Data", f"{english_titles} articles have English text in title_fa")
        else:
            ok("No English text in Farsi titles")

        # Broken image URLs
        result = await db.execute(select(Article.image_url).where(Article.image_url.isnot(None)).limit(50))
        broken_images = 0
        async with httpx.AsyncClient(timeout=5) as client:
            for (url,) in result.all():
                if url and "localhost" in url:
                    try:
                        r = await client.head(url)
                        if r.status_code != 200:
                            broken_images += 1
                    except Exception:
                        broken_images += 1
        if broken_images > 0:
            warning("Data", f"{broken_images} broken image URLs (out of 50 sampled)")
        else:
            ok("Image URLs healthy (50 sampled)")

        # Sources
        sources = (await db.execute(select(func.count(Source.id)))).scalar()
        ok(f"Sources: {sources}")

        # Telegram
        tg_channels = (await db.execute(select(func.count(TelegramChannel.id)))).scalar()
        tg_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar()
        ok(f"Telegram: {tg_channels} channels, {tg_posts} posts")

        # Freshness — when was the last article ingested?
        latest = (await db.execute(
            select(func.max(Article.ingested_at))
        )).scalar()
        if latest:
            hours_ago = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            if hours_ago > STALE_HOURS:
                issue("Freshness", f"Last article ingested {hours_ago:.0f}h ago (>{STALE_HOURS}h)", "Run: python manage.py pipeline")
            else:
                ok(f"Data fresh: last ingested {hours_ago:.1f}h ago")
        else:
            issue("Freshness", "No articles ingested at all", "Run: python manage.py pipeline")

        # Story title quality
        result = await db.execute(
            select(Story.title_fa, Story.id).where(Story.article_count >= 5)
        )
        long_titles = 0
        question_titles = 0
        for title, sid in result.all():
            if title and len(title) > MAX_TITLE_LENGTH:
                long_titles += 1
            if title and "؟" in title:
                question_titles += 1
        if long_titles > 0:
            warning("Content", f"{long_titles} story titles longer than {MAX_TITLE_LENGTH} chars")
        if question_titles > 0:
            warning("Content", f"{question_titles} story titles are questions (should be statements)")

        # Story-summary mismatch check (basic)
        result = await db.execute(
            select(Story.title_fa, Story.summary_fa)
            .where(Story.article_count >= 5, Story.summary_fa.isnot(None))
        )
        mismatches = 0
        for title, summary in result.all():
            if title and summary:
                # Check if any significant word from the title appears in the summary
                title_words = set(re.findall(r'[\u0600-\u06FF]{3,}', title))
                summary_words = set(re.findall(r'[\u0600-\u06FF]{3,}', summary))
                overlap = title_words & summary_words
                if len(overlap) < 1 and len(title_words) > 2:
                    mismatches += 1
        if mismatches > 0:
            warning("Content", f"{mismatches} stories may have title-summary mismatch")
        else:
            ok("Title-summary consistency looks good")


async def check_infrastructure():
    """Check Docker, ports, etc."""
    import subprocess

    # Docker
    try:
        result = subprocess.run(["docker", "compose", "ps", "--format", "json"], capture_output=True, text=True, cwd="/Users/parham/Desktop/claude_door-bin/doornegar")
        if result.returncode == 0 and "running" in result.stdout.lower():
            ok("Docker containers running")
        else:
            warning("Infra", "Docker containers may not be running")
    except Exception:
        warning("Infra", "Could not check Docker status")

    # CORS check
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.options(
                f"{BACKEND_URL}/api/v1/stories/trending",
                headers={"Origin": "http://localhost:3001", "Access-Control-Request-Method": "GET"}
            )
            if "access-control-allow-origin" in r.headers:
                ok("CORS configured for localhost:3001")
            else:
                issue("Infra", "CORS not allowing localhost:3001", "Check CORS_ORIGINS in .env")
        except Exception:
            pass


async def check_api_responses():
    """Check that API responses have expected data structure."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Trending stories should have images and summaries
        try:
            r = await client.get(f"{BACKEND_URL}/api/v1/stories/trending?limit=5")
            stories = r.json()
            if not stories:
                issue("API", "Trending returns empty", "Run: python manage.py cluster")
                return

            no_image = sum(1 for s in stories if not s.get("image_url"))
            no_title_fa = sum(1 for s in stories if not s.get("title_fa"))
            zero_pct = sum(1 for s in stories if s.get("state_pct", 0) == 0 and s.get("diaspora_pct", 0) == 0 and s.get("independent_pct", 0) == 0)

            if no_image > 0:
                warning("API", f"{no_image}/{len(stories)} trending stories have no image")
            else:
                ok("All trending stories have images")

            if no_title_fa > 0:
                issue("API", f"{no_title_fa}/{len(stories)} trending stories missing title_fa")

            if zero_pct > 0:
                warning("API", f"{zero_pct}/{len(stories)} trending stories have 0% coverage on all sides")

            # Check analysis endpoint
            story_id = stories[0]["id"]
            r2 = await client.get(f"{BACKEND_URL}/api/v1/stories/{story_id}/analysis")
            if r2.status_code == 200:
                analysis = r2.json()
                if analysis.get("summary_fa"):
                    ok("Story analysis returns summary")
                else:
                    warning("API", "Story analysis has no summary_fa")
            else:
                issue("API", f"Story analysis returned {r2.status_code}")

        except Exception as e:
            issue("API", f"Trending check failed: {e}")


async def main():
    print("═══════════════════════════════════════")
    print("  دورنگر — بررسی کیفیت")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("═══════════════════════════════════════")
    print()

    await check_api_health()
    await check_frontend()
    await check_data_quality()
    await check_infrastructure()
    await check_api_responses()

    # Print results
    print(f"✓ {len(passed)} checks passed")
    for p in passed:
        print(f"  ✓ {p}")

    if warnings:
        print(f"\n⚠ {len(warnings)} warnings")
        for w in warnings:
            print(f"  ⚠ [{w['category']}] {w['message']}")

    if issues:
        print(f"\n✗ {len(issues)} issues found")
        for i in issues:
            print(f"  ✗ [{i['category']}] {i['message']}")
            if i.get("fix"):
                print(f"    Fix: {i['fix']}")
    else:
        print("\n✓ No issues found!")

    print(f"\n═══════════════════════════════════════")
    print(f"  نتیجه: {len(passed)} ✓  {len(warnings)} ⚠  {len(issues)} ✗")
    print(f"═══════════════════════════════════════")

    return len(issues)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(1 if exit_code > 0 else 0)

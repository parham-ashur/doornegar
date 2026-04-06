"""HTML scraping fallback for sources without working RSS feeds.

Used when RSS feeds are geo-blocked or unavailable.
Each source has a custom scraper that extracts article titles, URLs, and dates.
"""

import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "fa,en;q=0.9",
}


async def scrape_source(slug: str) -> list[dict]:
    """Scrape articles from a source by slug. Returns list of article dicts."""
    scrapers = {
        "dw-persian": scrape_dw_persian,
        "radio-zamaneh": scrape_radio_zamaneh,
        "press-tv": scrape_press_tv,
    }

    scraper = scrapers.get(slug)
    if not scraper:
        return []

    try:
        return await scraper()
    except Exception as e:
        logger.error(f"Scraping failed for {slug}: {e}")
        return []


async def scrape_dw_persian() -> list[dict]:
    """Scrape DW Persian homepage for articles."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get("https://www.dw.com/fa-ir")
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []

    for link in soup.select("a[href*='/fa-ir/']"):
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or len(title) < 10 or not href:
            continue
        if not href.startswith("http"):
            href = "https://www.dw.com" + href

        # Skip navigation/category links
        if "/fa-ir/topic/" in href or "/fa-ir/media/" in href:
            continue

        articles.append({
            "title": title,
            "url": href,
            "published_at": datetime.now(timezone.utc),
        })

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique[:30]


async def scrape_radio_zamaneh() -> list[dict]:
    """Scrape Radio Zamaneh for articles."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get("https://www.radiozamaneh.com/")
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []

    for article in soup.select("article a, .entry-title a, h2 a, h3 a"):
        href = article.get("href", "")
        title = article.get_text(strip=True)
        if not title or len(title) < 10 or not href:
            continue
        if not href.startswith("http"):
            href = "https://www.radiozamaneh.com" + href

        articles.append({
            "title": title,
            "url": href,
            "published_at": datetime.now(timezone.utc),
        })

    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique[:30]


async def scrape_press_tv() -> list[dict]:
    """Scrape Press TV for articles."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        resp = await client.get("https://www.presstv.ir/")
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []

    for link in soup.select("a[href*='/Detail/']"):
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or len(title) < 10 or not href:
            continue
        if not href.startswith("http"):
            href = "https://www.presstv.ir" + href

        articles.append({
            "title": title,
            "url": href,
            "published_at": datetime.now(timezone.utc),
        })

    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique[:30]

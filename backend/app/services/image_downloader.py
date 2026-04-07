"""Download and store article images locally.

Replaces remote image URLs with local paths served by FastAPI.
Handles expired Telegram CDN links and other transient URLs.
"""

import hashlib
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

IMAGES_DIR = Path(__file__).parent.parent.parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Base URL for serving images
LOCAL_IMAGE_BASE = f"http://localhost:{settings.port}/images"


def _image_filename(url: str) -> str:
    """Generate a deterministic filename from URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    # Try to preserve extension
    ext = ".jpg"
    for e in [".jpg", ".jpeg", ".png", ".webp"]:
        if e in url.lower():
            ext = e
            break
    return f"{url_hash}{ext}"


async def download_image(url: str) -> str | None:
    """Download an image and save locally. Returns local URL or None."""
    if not url or url.startswith(LOCAL_IMAGE_BASE):
        return url  # Already local

    filename = _image_filename(url)
    filepath = IMAGES_DIR / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 1000:
        return f"{LOCAL_IMAGE_BASE}/{filename}"

    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/0.1)"},
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None

            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None

            # Save file
            filepath.write_bytes(response.content)
            logger.debug(f"Downloaded image: {filename} ({len(response.content)} bytes)")
            return f"{LOCAL_IMAGE_BASE}/{filename}"

    except Exception as e:
        logger.debug(f"Failed to download image {url[:60]}: {e}")
        return None


async def download_all_article_images(db) -> dict:
    """Download images for all articles that have remote URLs.

    Returns stats: {downloaded, failed, already_local, no_image}
    """
    from sqlalchemy import select
    from app.models.article import Article

    result = await db.execute(select(Article).where(Article.image_url.isnot(None)))
    articles = list(result.scalars().all())

    stats = {"downloaded": 0, "failed": 0, "already_local": 0, "no_image": 0}

    for article in articles:
        if not article.image_url:
            stats["no_image"] += 1
            continue

        if article.image_url.startswith(LOCAL_IMAGE_BASE):
            stats["already_local"] += 1
            continue

        local_url = await download_image(article.image_url)
        if local_url:
            article.image_url = local_url
            stats["downloaded"] += 1
        else:
            article.image_url = None  # Clear broken URL
            stats["failed"] += 1

    await db.commit()
    return stats

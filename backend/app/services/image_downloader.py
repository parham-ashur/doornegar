"""Download article images and store them in Cloudflare R2.

Falls back to local storage if R2 is not configured (useful for local dev).
Replaces remote image URLs with permanent, CDN-backed R2 URLs.
"""

import hashlib
import logging
import mimetypes
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Local fallback directory (used if R2 not configured)
IMAGES_DIR = Path(__file__).parent.parent.parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Base URL for serving images — relative so frontend prepends API host
LOCAL_IMAGE_BASE = "/images"


def _is_r2_configured() -> bool:
    return bool(
        settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_account_id
        and settings.r2_public_url
    )


def _image_filename(url: str) -> str:
    """Generate a deterministic filename from URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    ext = ".jpg"
    for e in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if e in url.lower():
            ext = e
            break
    return f"{url_hash}{ext}"


async def _upload_to_r2(filename: str, content: bytes, content_type: str) -> str | None:
    """Upload bytes to R2 and return the public URL."""
    try:
        import aioboto3

        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        ) as s3:
            await s3.put_object(
                Bucket=settings.r2_bucket_name,
                Key=filename,
                Body=content,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
        return f"{settings.r2_public_url.rstrip('/')}/{filename}"
    except Exception as e:
        logger.warning(f"R2 upload failed for {filename}: {e}")
        return None


async def _object_exists_in_r2(filename: str) -> bool:
    """Check if an object already exists in R2."""
    try:
        import aioboto3

        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        ) as s3:
            await s3.head_object(Bucket=settings.r2_bucket_name, Key=filename)
            return True
    except Exception:
        return False


async def download_image(url: str) -> str | None:
    """Download an image and store it. Returns permanent URL (R2 or local) or None."""
    if not url:
        return None

    # Already a final URL (R2 or local)
    if url.startswith(LOCAL_IMAGE_BASE):
        return url
    if settings.r2_public_url and url.startswith(settings.r2_public_url):
        return url

    filename = _image_filename(url)

    # If R2 is configured, upload there
    if _is_r2_configured():
        # Skip if already in R2
        if await _object_exists_in_r2(filename):
            return f"{settings.r2_public_url.rstrip('/')}/{filename}"

        # Download source image
        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/1.0)"},
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "image/jpeg")
                if not content_type.startswith("image/"):
                    return None
                content = response.content
                if len(content) < 1000:  # Too small, probably a placeholder
                    return None
        except Exception as e:
            logger.debug(f"Download failed {url[:60]}: {e}")
            return None

        return await _upload_to_r2(filename, content, content_type)

    # Fallback: save locally
    filepath = IMAGES_DIR / filename
    if filepath.exists() and filepath.stat().st_size > 1000:
        return f"{LOCAL_IMAGE_BASE}/{filename}"
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Doornegar/1.0)"},
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None
            filepath.write_bytes(response.content)
            return f"{LOCAL_IMAGE_BASE}/{filename}"
    except Exception as e:
        logger.debug(f"Local download failed {url[:60]}: {e}")
        return None


async def download_all_article_images(db) -> dict:
    """Download images for all articles that have remote URLs."""
    from sqlalchemy import select

    from app.models.article import Article

    result = await db.execute(select(Article).where(Article.image_url.isnot(None)))
    articles = list(result.scalars().all())

    stats = {"downloaded": 0, "failed": 0, "already_stored": 0, "no_image": 0}

    for article in articles:
        if not article.image_url:
            stats["no_image"] += 1
            continue

        # Already stored in R2 or locally
        if article.image_url.startswith(LOCAL_IMAGE_BASE) or (
            settings.r2_public_url and article.image_url.startswith(settings.r2_public_url)
        ):
            stats["already_stored"] += 1
            continue

        stored_url = await download_image(article.image_url)
        if stored_url:
            article.image_url = stored_url
            stats["downloaded"] += 1
        else:
            article.image_url = None
            stats["failed"] += 1

    await db.commit()
    return stats

"""Download article images, recompress to WebP, and store them in Cloudflare R2.

Falls back to local storage if R2 is not configured (useful for local dev).
Replaces remote image URLs with permanent, CDN-backed R2 URLs at a sensible
size (max 1600px wide) and modern format (WebP @ q75) — frontend then runs
those through Vercel's `/_next/image` optimizer for further per-viewport
sizing. Bypasses Iranian-source CDN geo-blocks (the Iranian sites that
refuse Vercel's IPs accept Railway's, so we proxy through here).
"""

import hashlib
import io
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

# Recompression targets. 1600px wide matches the existing HITL stock-image
# pin pattern (api/v1/hitl.py:632); WebP @ q75 averages ~30-40% smaller
# than JPEG @ q85 at indistinguishable visual quality on phone-sized cards.
REHOST_MAX_WIDTH = 1600
REHOST_WEBP_QUALITY = 75


def _is_r2_configured() -> bool:
    return bool(
        settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_account_id
        and settings.r2_public_url
    )


def _image_filename(url: str, ext: str = ".webp") -> str:
    """Deterministic filename from URL. Defaults to .webp because re-hosted
    images are recompressed to that format. Pass a different ext for the
    pass-through path when Pillow can't decode the source bytes."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return f"{url_hash}{ext}"


def _recompress_to_webp(content: bytes) -> tuple[bytes, str] | None:
    """Resize to <=1600px wide and re-encode as WebP. Returns (bytes, content_type)
    on success, None when Pillow can't decode (SVG, animated GIF, malformed).
    Animated GIFs go through the pass-through branch — Pillow's `save("WEBP")` on
    a multi-frame Image only writes the first frame, which would silently break
    the asset; better to keep the original bytes."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(content))
        # Animated GIFs: punt to raw upload — see docstring.
        if getattr(img, "is_animated", False):
            return None
        img.load()
        if img.mode in ("P", "LA", "RGBA"):
            # Flatten transparency to white. Story cards never need alpha and
            # WebP-with-alpha is a noticeable size cost.
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if w > REHOST_MAX_WIDTH:
            new_h = int(h * REHOST_MAX_WIDTH / w)
            img = img.resize((REHOST_MAX_WIDTH, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=REHOST_WEBP_QUALITY, method=6)
        return buf.getvalue(), "image/webp"
    except Exception as e:
        logger.debug(f"Pillow recompress failed (will fall back to raw): {e}")
        return None


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
    """Download an image, resize+recompress to WebP, store in R2 (or locally).

    Returns the permanent URL (R2 or local) or None if download/encode failed.
    Already-hosted URLs are returned unchanged. Source bytes that Pillow can't
    decode (SVG, animated GIF, malformed) are passed through with their
    original extension preserved."""
    if not url:
        return None

    # Already a final URL (R2 or local)
    if url.startswith(LOCAL_IMAGE_BASE):
        return url
    if settings.r2_public_url and url.startswith(settings.r2_public_url):
        return url

    # Default to .webp filename; we'll switch to the source ext below if
    # recompression isn't possible.
    webp_filename = _image_filename(url, ext=".webp")

    # If R2 is configured, upload there
    if _is_r2_configured():
        # Already recompressed and in R2
        if await _object_exists_in_r2(webp_filename):
            return f"{settings.r2_public_url.rstrip('/')}/{webp_filename}"

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

        # Try to recompress to WebP; fall back to raw upload if Pillow can't
        # handle the format (SVG, animated GIF). Saves ~40-70% on the typical
        # 600KB Iranian-source JPEG hero.
        recompressed = _recompress_to_webp(content)
        if recompressed is not None:
            new_bytes, new_content_type = recompressed
            return await _upload_to_r2(webp_filename, new_bytes, new_content_type)

        # Pass-through path: keep the original bytes + ext.
        ext = ".jpg"
        for e in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            if e in url.lower():
                ext = e
                break
        raw_filename = _image_filename(url, ext=ext)
        if await _object_exists_in_r2(raw_filename):
            return f"{settings.r2_public_url.rstrip('/')}/{raw_filename}"
        return await _upload_to_r2(raw_filename, content, content_type)

    # Fallback: save locally (dev only). Skip recompression for simplicity —
    # the local dev loop doesn't need byte-for-byte parity with prod.
    legacy_filename = _image_filename(url, ext=".jpg")
    filepath = IMAGES_DIR / legacy_filename
    if filepath.exists() and filepath.stat().st_size > 1000:
        return f"{LOCAL_IMAGE_BASE}/{legacy_filename}"
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
            return f"{LOCAL_IMAGE_BASE}/{legacy_filename}"
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

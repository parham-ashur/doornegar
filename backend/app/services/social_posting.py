"""Social media posting service.

Generates and posts content to multiple platforms:
- Telegram Channel
- Twitter/X
- Instagram (via Meta Business API)
- WhatsApp Business (broadcast lists)
- Bluesky
- LinkedIn

Tracks what's been posted to avoid duplicates.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.story import Story

logger = logging.getLogger(__name__)

POSTED_FILE = Path(__file__).parent.parent.parent / "posted_stories.json"
PLATFORMS = ["telegram", "twitter", "instagram", "whatsapp", "bluesky", "linkedin"]


def _load_posted() -> dict:
    if POSTED_FILE.exists():
        try:
            return json.loads(POSTED_FILE.read_text())
        except Exception:
            pass
    return {p: [] for p in PLATFORMS}


def _save_posted(data: dict):
    POSTED_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _mark_posted(story_id: str, platform: str):
    posted = _load_posted()
    posted.setdefault(platform, []).append(story_id)
    # Keep last 500 per platform
    for p in PLATFORMS:
        if p in posted:
            posted[p] = posted[p][-500:]
    _save_posted(posted)


# ─── Post generation ───────────────────────────────────────────────

def generate_post(story: Story, summary: str | None, platform: str) -> str:
    """Generate platform-specific post text."""
    title = story.title_fa or story.title_en or "بدون عنوان"

    # Truncate summary
    text = summary or ""
    if len(text) > 250:
        cut = text[:250]
        last_dot = max(cut.rfind("."), cut.rfind("،"), cut.rfind("؛"))
        text = cut[:last_dot + 1] if last_dot > 100 else cut + "..."

    coverage = []
    if story.covered_by_state:
        coverage.append("حکومتی")
    if story.covered_by_diaspora:
        coverage.append("برون‌مرزی")
    coverage_str = " · ".join(coverage)

    blindspot = ""
    if story.is_blindspot:
        if story.blindspot_type == "state_only":
            blindspot = "\n🔴 نقطه کور: فقط رسانه‌های حکومتی پوشش داده‌اند"
        elif story.blindspot_type == "diaspora_only":
            blindspot = "\n🔵 نقطه کور: فقط رسانه‌های برون‌مرزی پوشش داده‌اند"

    tags = "#دورنگر #شفافیت_رسانه #ایران"

    if platform == "telegram":
        post = f"📰 **{title}**\n\n"
        if text:
            post += f"{text}\n\n"
        post += f"📊 {story.source_count} رسانه · {story.article_count} مقاله"
        if coverage_str:
            post += f" · {coverage_str}"
        if blindspot:
            post += f"\n{blindspot}"
        post += f"\n\n{tags}"
        return post

    elif platform == "twitter":
        # 280 char limit
        post = f"📰 {title}\n\n"
        remaining = 280 - len(post) - len(tags) - 5
        if text and remaining > 50:
            post += text[:remaining] + "\n\n"
        post += tags
        return post[:280]

    elif platform == "instagram":
        # Instagram caption — can be long, add more hashtags
        post = f"📰 {title}\n\n"
        if text:
            post += f"{text}\n\n"
        post += f"📊 {story.source_count} رسانه · {story.article_count} مقاله\n"
        if coverage_str:
            post += f"پوشش: {coverage_str}\n"
        if blindspot:
            post += f"{blindspot}\n"
        post += f"\n{tags} #media_bias #iran_news #media_transparency #خبر #رسانه"
        return post

    elif platform == "whatsapp":
        # WhatsApp — plain text, no markdown
        post = f"📰 {title}\n\n"
        if text:
            post += f"{text}\n\n"
        post += f"{story.source_count} رسانه · {story.article_count} مقاله"
        if blindspot:
            post += f"\n{blindspot.replace('🔴', '⚠').replace('🔵', '⚠')}"
        post += "\n\nدورنگر — شفافیت رسانه‌ای ایران"
        return post

    elif platform == "bluesky":
        # 300 char limit, no markdown
        post = f"📰 {title}\n\n"
        remaining = 300 - len(post) - 30
        if text and remaining > 50:
            post += text[:remaining] + "\n\n"
        post += "#دورنگر #ایران"
        return post[:300]

    elif platform == "linkedin":
        # Professional tone, longer form
        post = f"📰 {title}\n\n"
        if text:
            post += f"{text}\n\n"
        post += f"Coverage: {story.source_count} sources · {story.article_count} articles\n"
        if blindspot:
            post += f"\n⚠️ Media blind spot detected — only one side is covering this story.\n"
        post += f"\n#MediaTransparency #Iran #MediaBias #Doornegar"
        return post

    return f"{title}\n{text}"


# ─── Platform-specific posting ─────────────────────────────────────

async def post_to_telegram(story_id: str, text: str) -> dict:
    """Post to Doornegar's Telegram channel."""
    if not settings.telegram_channel_username:
        return {"error": "TELEGRAM_CHANNEL_USERNAME not set"}
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        session = (
            StringSession(settings.telegram_session_string)
            if settings.telegram_session_string
            else "doornegar_session"
        )
        client = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            return {"error": "Telegram session expired"}
        await client.send_message(settings.telegram_channel_username, text, parse_mode="md")
        await client.disconnect()
        _mark_posted(story_id, "telegram")
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


async def post_to_twitter(story_id: str, text: str) -> dict:
    """Post to Twitter/X."""
    if not settings.twitter_api_key:
        return {"error": "Twitter API keys not configured"}
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=settings.twitter_api_key,
            consumer_secret=settings.twitter_api_secret,
            access_token=settings.twitter_access_token,
            access_token_secret=settings.twitter_access_token_secret,
        )
        r = client.create_tweet(text=text)
        _mark_posted(story_id, "twitter")
        return {"success": True, "tweet_id": str(r.data["id"])}
    except ImportError:
        return {"error": "Install: pip install tweepy"}
    except Exception as e:
        return {"error": str(e)}


async def post_to_instagram(story_id: str, text: str, image_url: str | None = None) -> dict:
    """Post to Instagram via Meta Business API. Requires an image."""
    if not settings.instagram_access_token or not settings.instagram_business_account_id:
        return {"error": "Instagram API not configured. Need: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID"}
    if not image_url:
        return {"error": "Instagram requires an image URL"}
    try:
        import httpx
        account_id = settings.instagram_business_account_id
        token = settings.instagram_access_token

        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Create media container
            r1 = await client.post(
                f"https://graph.facebook.com/v18.0/{account_id}/media",
                params={"image_url": image_url, "caption": text, "access_token": token},
            )
            container_id = r1.json().get("id")
            if not container_id:
                return {"error": f"Failed to create media: {r1.json()}"}

            # Step 2: Publish
            r2 = await client.post(
                f"https://graph.facebook.com/v18.0/{account_id}/media_publish",
                params={"creation_id": container_id, "access_token": token},
            )
            post_id = r2.json().get("id")
            if post_id:
                _mark_posted(story_id, "instagram")
                return {"success": True, "post_id": post_id}
            return {"error": f"Publish failed: {r2.json()}"}
    except Exception as e:
        return {"error": str(e)}


async def post_to_whatsapp(story_id: str, text: str) -> dict:
    """Send to WhatsApp Business API (broadcast to a template or group)."""
    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        return {"error": "WhatsApp API not configured. Need: WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN"}
    # Note: WhatsApp Business API requires pre-approved message templates for broadcast.
    # For now, this saves the post for manual sharing.
    _mark_posted(story_id, "whatsapp")
    return {"success": True, "note": "WhatsApp requires template approval for broadcast. Post text saved for manual sharing.", "text": text}


async def post_to_bluesky(story_id: str, text: str) -> dict:
    """Post to Bluesky."""
    if not settings.bluesky_handle or not settings.bluesky_app_password:
        return {"error": "Bluesky not configured. Need: BLUESKY_HANDLE, BLUESKY_APP_PASSWORD"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            # Login
            r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={
                "identifier": settings.bluesky_handle,
                "password": settings.bluesky_app_password,
            })
            session = r.json()
            if "accessJwt" not in session:
                return {"error": f"Login failed: {session}"}

            # Create post
            r2 = await client.post(
                "https://bsky.social/xrpc/com.atproto.repo.createRecord",
                headers={"Authorization": f"Bearer {session['accessJwt']}"},
                json={
                    "repo": session["did"],
                    "collection": "app.bsky.feed.post",
                    "record": {
                        "$type": "app.bsky.feed.post",
                        "text": text,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
            if r2.status_code == 200:
                _mark_posted(story_id, "bluesky")
                return {"success": True}
            return {"error": f"Post failed: {r2.json()}"}
    except Exception as e:
        return {"error": str(e)}


async def post_to_linkedin(story_id: str, text: str) -> dict:
    """Post to LinkedIn organization page."""
    if not settings.linkedin_access_token or not settings.linkedin_org_id:
        return {"error": "LinkedIn not configured. Need: LINKEDIN_ACCESS_TOKEN, LINKEDIN_ORG_ID"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {settings.linkedin_access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "author": f"urn:li:organization:{settings.linkedin_org_id}",
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {"text": text},
                            "shareMediaCategory": "NONE",
                        }
                    },
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                },
            )
            if r.status_code in (200, 201):
                _mark_posted(story_id, "linkedin")
                return {"success": True}
            return {"error": f"Post failed ({r.status_code}): {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Unified posting ───────────────────────────────────────────────

POSTERS = {
    "telegram": post_to_telegram,
    "twitter": post_to_twitter,
    "instagram": post_to_instagram,
    "whatsapp": post_to_whatsapp,
    "bluesky": post_to_bluesky,
    "linkedin": post_to_linkedin,
}


async def post_story(story_id: str, platform: str, text: str, **kwargs) -> dict:
    """Post to any platform."""
    poster = POSTERS.get(platform)
    if not poster:
        return {"error": f"Unknown platform: {platform}. Options: {', '.join(POSTERS.keys())}"}
    return await poster(story_id, text, **kwargs)


async def get_post_preview(db: AsyncSession, limit: int = 5) -> list[dict]:
    """Generate previews of what would be posted (for review)."""
    posted = _load_posted()
    all_posted = set()
    for ids in posted.values():
        all_posted.update(ids)

    result = await db.execute(
        select(Story)
        .where(Story.article_count >= 5, Story.summary_fa.isnot(None))
        .order_by(Story.trending_score.desc())
        .limit(limit + len(all_posted))
    )

    queue = []
    for story in result.scalars().all():
        sid = str(story.id)
        if sid in all_posted:
            continue
        if len(queue) >= limit:
            break

        item = {
            "story_id": sid,
            "title": story.title_fa,
            "image_url": None,  # Would need to look up from articles
            "posts": {},
        }
        for platform in PLATFORMS:
            item["posts"][platform] = generate_post(story, story.summary_fa, platform)

        # Check which platforms haven't posted this yet
        item["not_posted_on"] = [p for p in PLATFORMS if sid not in posted.get(p, [])]

        queue.append(item)

    return queue


async def get_platform_status() -> dict:
    """Check which platforms are configured."""
    return {
        "telegram": {"configured": bool(settings.telegram_channel_username), "needs": "TELEGRAM_CHANNEL_USERNAME"},
        "twitter": {"configured": bool(settings.twitter_api_key), "needs": "TWITTER_API_KEY + 3 more keys"},
        "instagram": {"configured": bool(settings.instagram_access_token), "needs": "INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID"},
        "whatsapp": {"configured": bool(settings.whatsapp_access_token), "needs": "WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN"},
        "bluesky": {"configured": bool(settings.bluesky_handle), "needs": "BLUESKY_HANDLE, BLUESKY_APP_PASSWORD"},
        "linkedin": {"configured": bool(settings.linkedin_access_token), "needs": "LINKEDIN_ACCESS_TOKEN, LINKEDIN_ORG_ID"},
    }

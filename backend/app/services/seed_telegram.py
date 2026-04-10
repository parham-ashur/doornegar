"""Seed initial Telegram channels to track.

These are major public Persian-language Telegram channels that discuss
Iranian news. All are public channels with open access.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import TelegramChannel

logger = logging.getLogger(__name__)

INITIAL_CHANNELS = [
    # News outlet official channels
    {
        "username": "bbcpersian",
        "title": "BBC فارسی",
        "channel_type": "news",
        "political_leaning": "neutral",
        "language": "fa",
        "description": "Official BBC Persian Telegram channel",
    },
    {
        "username": "iranintl_fa",
        "title": "Iran International ایران اینترنشنال",
        "channel_type": "news",
        "political_leaning": "opposition",
        "language": "fa",
        "description": "Iran International news channel",
    },
    {
        "username": "Tasnimnews",
        "title": "Tasnim News",
        "channel_type": "news",
        "political_leaning": "pro_regime",
        "language": "fa",
        "description": "Tasnim News Agency (IRGC-affiliated)",
    },
    {
        "username": "farsna",
        "title": "Fars News",
        "channel_type": "news",
        "political_leaning": "pro_regime",
        "language": "fa",
        "description": "Fars News Agency (IRGC-affiliated)",
    },
    # Commentary/analysis channels
    {
        "username": "radiozamaneh",
        "title": "رادیو زمانه",
        "channel_type": "news",
        "political_leaning": "reformist",
        "language": "fa",
        "description": "Radio Zamaneh Telegram channel",
    },
    {
        "username": "presstv",
        "title": "Press TV",
        "channel_type": "news",
        "political_leaning": "pro_regime",
        "language": "en",
        "description": "Press TV state-funded English channel",
    },
    {
        "username": "radiofarda",
        "title": "رادیو فردا",
        "channel_type": "news",
        "political_leaning": "opposition",
        "language": "fa",
        "description": "Radio Farda (RFE/RL) Telegram channel",
    },
    {
        "username": "zeitoons",
        "title": "زیتون",
        "channel_type": "commentary",
        "political_leaning": "reformist",
        "language": "fa",
        "description": "Zeitoons independent media — civil society focus",
    },
    {
        "username": "khabaronline_ir",
        "title": "خبرآنلاین",
        "channel_type": "news",
        "political_leaning": "moderate",
        "language": "fa",
        "description": "Khabar Online news channel — inside Iran",
    },
]


async def seed_telegram_channels(db: AsyncSession) -> int:
    """Seed initial Telegram channels. Returns count of newly created."""
    created = 0
    for channel_data in INITIAL_CHANNELS:
        existing = await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.username == channel_data["username"]
            )
        )
        if existing.scalar_one_or_none() is None:
            channel = TelegramChannel(**channel_data)
            db.add(channel)
            created += 1
            logger.info(f"Created Telegram channel: @{channel_data['username']}")

    await db.commit()
    logger.info(f"Telegram seeding complete: {created} new channels")
    return created

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
        "username": "iranaborigen",
        "title": "Iran International ایران اینترنشنال",
        "channel_type": "news",
        "political_leaning": "opposition",
        "language": "fa",
        "description": "Iran International news channel",
    },
    {
        "username": "tasaborgen",
        "title": "Tasnim News",
        "channel_type": "news",
        "political_leaning": "pro_regime",
        "language": "fa",
        "description": "Tasnim News Agency (IRGC-affiliated)",
    },
    {
        "username": "faraborgen",
        "title": "Fars News",
        "channel_type": "news",
        "political_leaning": "pro_regime",
        "language": "fa",
        "description": "Fars News Agency (IRGC-affiliated)",
    },
    # Commentary/analysis channels
    {
        "username": "iranwirefarsi",
        "title": "IranWire فارسی",
        "channel_type": "commentary",
        "political_leaning": "opposition",
        "language": "fa",
        "description": "IranWire independent news and analysis",
    },
    {
        "username": "radiozamaneh",
        "title": "رادیو زمانه",
        "channel_type": "news",
        "political_leaning": "reformist",
        "language": "fa",
        "description": "Radio Zamaneh Telegram channel",
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

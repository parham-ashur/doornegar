"""Remove Telegram channels with wrong usernames."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BROKEN = [
    "iranaborigen", "tasaborgen", "faraborgen", "dwfarsi", "rfipersian",
    "iranintl", "MohammadMosaed", "iraborz", "Tabnak_ir", "VOAIran",
    "RadioFarda_", "manaborz", "IranWireFA",
]

async def main():
    from sqlalchemy import delete, select
    from app.database import async_session
    from app.models.social import TelegramChannel

    async with async_session() as db:
        for username in BROKEN:
            # Find channel
            ch = await db.execute(
                select(TelegramChannel).where(TelegramChannel.username == username)
            )
            channel = ch.scalar_one_or_none()
            if not channel:
                print(f"Not found: @{username}")
                continue
            # Delete posts first
            from app.models.social import TelegramPost
            posts_del = await db.execute(
                delete(TelegramPost).where(TelegramPost.channel_id == channel.id)
            )
            # Then delete channel
            await db.execute(
                delete(TelegramChannel).where(TelegramChannel.id == channel.id)
            )
            print(f"Removed @{username} ({posts_del.rowcount} posts)")
        await db.commit()

        # Show remaining count
        count = await db.execute(select(TelegramChannel))
        channels = count.scalars().all()
        print(f"\n{len(channels)} channels remaining")

if __name__ == "__main__":
    asyncio.run(main())

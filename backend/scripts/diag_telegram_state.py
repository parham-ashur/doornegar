"""Diagnostic: why are there 0 new Telegram posts in the last 24h?

Possible root causes:
  (a) session string expired / deauthorized
  (b) Telethon cannot connect from Railway
  (c) all 44 channels have genuinely gone silent
  (d) ingest_all_channels crashes before writing
  (e) ingestion cron is not firing the Telegram step

This is read-only — connects to the Telegram API briefly to confirm
auth works, but does not write anything to the DB or Telegram.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from sqlalchemy import func, select
    from app.config import settings
    from app.database import async_session
    from app.models.social import TelegramChannel, TelegramPost

    now = datetime.now(timezone.utc)

    async with async_session() as db:
        print("=== Telegram channel roster ===")
        total = (await db.execute(select(func.count(TelegramChannel.id)))).scalar() or 0
        active = (await db.execute(
            select(func.count(TelegramChannel.id)).where(TelegramChannel.is_active.is_(True))
        )).scalar() or 0
        print(f"  total channels: {total}")
        print(f"  active:         {active}")

        print("\n=== Posts by age window ===")
        windows = [
            ("<1h",  now - timedelta(hours=1)),
            ("<6h",  now - timedelta(hours=6)),
            ("<24h", now - timedelta(hours=24)),
            ("<48h", now - timedelta(hours=48)),
            ("<7d",  now - timedelta(days=7)),
            ("<30d", now - timedelta(days=30)),
        ]
        for label, cutoff in windows:
            n = (await db.execute(
                select(func.count(TelegramPost.id)).where(TelegramPost.created_at >= cutoff)
            )).scalar() or 0
            print(f"  {label:>6} posts: {n}")

        total_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar() or 0
        print(f"  total posts:    {total_posts}")

        last_post = (await db.execute(
            select(TelegramPost.created_at, TelegramPost.date, TelegramPost.channel_id)
            .order_by(TelegramPost.created_at.desc())
            .limit(1)
        )).one_or_none()
        if last_post:
            age = (now - last_post.created_at).total_seconds() / 3600
            print(f"\n  newest post created_at: {last_post.created_at}  ({age:.1f}h ago)")
            print(f"  its telegram date:      {last_post.date}")

        print("\n=== Last-fetched timestamp per channel (top 10 oldest) ===")
        rows = (await db.execute(
            select(
                TelegramChannel.username,
                TelegramChannel.is_active,
                TelegramChannel.last_fetched_at,
                TelegramChannel.last_message_id,
            )
            .where(TelegramChannel.is_active.is_(True))
            .order_by(TelegramChannel.last_fetched_at.asc().nullsfirst())
            .limit(10)
        )).all()
        for r in rows:
            last_check = r.last_fetched_at.isoformat() if r.last_fetched_at else "never"
            print(f"  {r.username:30s}  active={r.is_active!s:5s}  last_fetched={last_check}  last_msg_id={r.last_message_id}")

        print("\n=== Session config ===")
        print(f"  telegram_session_string set: {bool(settings.telegram_session_string)}")
        print(f"    length: {len(settings.telegram_session_string or '')}")
        print(f"  telegram_api_id set: {bool(settings.telegram_api_id)}")
        print(f"  telegram_api_hash set: {bool(settings.telegram_api_hash)}")

    # Live Telethon connectivity probe
    print("\n=== Live Telethon connection probe ===")
    try:
        from app.services.telegram_service import _get_telegram_client
        client = await _get_telegram_client()
        me = await client.get_me()
        print(f"  connected. authorized as: id={me.id} username={getattr(me, 'username', None)}")
        # Try fetching 1 message from one active channel
        try:
            # Pick first active channel with a username
            async with async_session() as db:
                row = (await db.execute(
                    select(TelegramChannel.username)
                    .where(TelegramChannel.is_active.is_(True))
                    .limit(1)
                )).one_or_none()
            if row:
                handle = row.username
                print(f"  attempting iter_messages on: {handle}")
                msgs_seen = 0
                async for msg in client.iter_messages(handle, limit=2):
                    msgs_seen += 1
                    print(f"    message id={msg.id}  date={msg.date}  text_len={len(msg.message or '')}")
                if msgs_seen == 0:
                    print("    no messages returned (empty channel or silent failure)")
            else:
                print("  no active channels to probe")
        except Exception as e:
            print(f"  iter_messages EXCEPTION: {type(e).__name__}: {e}")
        await client.disconnect()
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

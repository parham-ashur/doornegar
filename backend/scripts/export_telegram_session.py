"""Convert the local Telethon file session to a StringSession you can paste
into Railway's TELEGRAM_SESSION_STRING env var.

Why: on Railway the filesystem wipes between deploys, so a file-based
session doesn't persist. StringSession serializes everything the client
needs (auth key, user id, DC info) into a base64 string that fits in an
env var.

After exporting, this script DELETES the local session file by default.
The deletion is critical: keeping the file means any local Python that
imports app.services.telegram_service or runs a script with TelegramClient(
"doornegar_session", ...) will reconnect with the same auth key from a
different IP than Railway, and Telegram will invalidate the session
(AuthKeyDuplicatedError) within seconds. The string is now the single
source of truth — pass --keep-local to override.

Usage:
    python scripts/export_telegram_session.py [--keep-local]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import settings


SESSION_NAME = "doornegar_session"


async def main(keep_local: bool) -> int:
    api_id = int(settings.telegram_api_id or 0)
    api_hash = settings.telegram_api_hash or ""
    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID / TELEGRAM_API_HASH missing from .env", file=sys.stderr)
        return 1

    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print(
            "ERROR: local session isn't authorized. Run tg_auth_step1.py + tg_auth_step2.py first.",
            file=sys.stderr,
        )
        await client.disconnect()
        return 1

    # Sanity-prove the session actually works at the API level, not just
    # locally. If get_me succeeds we know the auth key is live.
    try:
        me = await client.get_me()
        print(f"Session confirmed live: id={me.id} username=@{getattr(me, 'username', '?')}")
    except Exception as e:
        print(f"ERROR: session looks authorized but get_me failed: {e}", file=sys.stderr)
        await client.disconnect()
        return 1

    string_session = StringSession.save(client.session)
    await client.disconnect()

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    session_file = os.path.join(backend_dir, f"{SESSION_NAME}.session")

    print()
    print("=" * 70)
    print("TELEGRAM_SESSION_STRING (paste as a Railway env var):")
    print("=" * 70)
    print(string_session)
    print("=" * 70)
    print()
    print(f"Length: {len(string_session)} chars")
    print()
    print("Set ONLY on the ingest-cron service (the Telegram authority):")
    print()
    print("    railway variables --service ingest-cron \\")
    print(f"      --set TELEGRAM_SESSION_STRING='{string_session}'")
    print()
    print("Other services (doornegar, maintenance-cron, rss-cron) should NOT")
    print("hold a session string. The TELEGRAM_AUTHORITY=true flag must stay")
    print("set on ingest-cron only.")
    print()

    if keep_local:
        print(f"Local session preserved at: {session_file}")
        print("WARNING: any local Telethon connect with this session will collide")
        print("with Railway and invalidate it. Re-run without --keep-local to clean up.")
    else:
        if os.path.exists(session_file):
            os.remove(session_file)
            print(f"Deleted local session file: {session_file}")
            print("(re-run tg_auth_step1.py + step2.py if you ever need a new one)")
    return 0


if __name__ == "__main__":
    keep_local = "--keep-local" in sys.argv
    sys.exit(asyncio.run(main(keep_local)))

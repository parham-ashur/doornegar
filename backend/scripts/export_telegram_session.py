"""Convert the local Telethon file session to a StringSession you can paste
into Railway's TELEGRAM_SESSION_STRING env var.

Why: on Railway the filesystem wipes between deploys, so a file-based
session doesn't persist. StringSession serializes everything the client
needs (auth key, user id, DC info) into a base64 string that fits in an
env var. Once set, the Railway cron container can connect to Telegram
without interactive phone auth.

Usage:
    python scripts/export_telegram_session.py

Then copy the printed string into Railway → doornegar service → Variables →
TELEGRAM_SESSION_STRING.

Requirements:
    - Local `doornegar_session.session` file exists (auth was already done)
    - TELEGRAM_API_ID and TELEGRAM_API_HASH env vars set (same values Railway uses)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import settings


async def main() -> int:
    api_id = int(settings.telegram_api_id or 0)
    api_hash = settings.telegram_api_hash or ""
    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID / TELEGRAM_API_HASH missing from .env", file=sys.stderr)
        return 1

    # Load the existing file-based session. This doesn't create a new one —
    # if doornegar_session.session doesn't exist, telethon will ask for auth
    # interactively (phone number, SMS code).
    client = TelegramClient("doornegar_session", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print(
            "ERROR: local session isn't authorized. Run `python manage.py telegram_auth`\n"
            "(or whatever script handles phone auth) first, then re-run this script.",
            file=sys.stderr,
        )
        return 1

    # Serialize the CURRENT session to a StringSession.
    string_session = StringSession.save(client.session)
    await client.disconnect()

    print()
    print("=" * 70)
    print("TELEGRAM_SESSION_STRING (paste as a Railway env var):")
    print("=" * 70)
    print(string_session)
    print("=" * 70)
    print()
    print(f"Length: {len(string_session)} chars")
    print()
    print("Next step: `railway variables --service doornegar --environment production \\")
    print("  --set TELEGRAM_SESSION_STRING='<paste>'`")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

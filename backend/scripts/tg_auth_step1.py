"""Step 1: Send Telegram auth code to phone.

Usage:
    python scripts/tg_auth_step1.py

Prints a phone_code_hash. Wait for the SMS code, then run:
    python scripts/tg_auth_step2.py <CODE> <PHONE_CODE_HASH>

If a stale local doornegar_session.session is present, this script
deletes it first — otherwise Telethon reuses the (likely dead) auth key
and either sends a code that doesn't actually re-authenticate or fails
silently. Re-auth is supposed to give us a fresh auth key.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

PHONE = "+33760552000"
SESSION_NAME = "doornegar_session"


async def main():
    # Wipe any prior local session so step 1 always starts from zero.
    # The dead session file is a footgun — it carries a dead auth key
    # whose channels list and connection metadata mislead the new run.
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    session_file = os.path.join(backend_dir, f"{SESSION_NAME}.session")
    if os.path.exists(session_file):
        os.remove(session_file)
        print(f"Removed stale {session_file}")

    from telethon import TelegramClient
    client = TelegramClient(
        SESSION_NAME,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    result = await client.send_code_request(PHONE)
    await client.disconnect()
    print()
    print(f"Code sent to {PHONE}.")
    print()
    print("Next, run:")
    print(f"    python scripts/tg_auth_step2.py <CODE_FROM_SMS> {result.phone_code_hash}")
    print()


if __name__ == "__main__":
    asyncio.run(main())

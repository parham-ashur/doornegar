"""One-time Telegram authentication script.

Usage:
    python scripts/telegram_auth.py

Interactive: the script prompts for phone number, SMS code, and 2FA
password (if enabled). All in one process so Telethon can hold the
phone_code_hash in memory between send_code_request and sign_in —
the previous two-step CLI flow lost that hash between invocations.

After this completes, doornegar_session.session is written to the
current directory. Then run scripts/export_telegram_session.py to
turn it into a StringSession to paste into Railway.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


async def main():
    from telethon import TelegramClient

    client = TelegramClient(
        "doornegar_session",
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    # client.start() handles connect → phone prompt → send code → code
    # prompt → 2FA prompt (if any) in a single interactive flow.
    await client.start()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\nAuthentication successful!")
        print(f"Logged in as: {me.first_name} (ID: {me.id})")
        print(f"Session file: doornegar_session.session")
        print(f"\nNext: python scripts/export_telegram_session.py")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

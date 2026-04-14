"""Step 1: Send Telegram auth code to phone."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

PHONE = "+33760552000"

async def main():
    from telethon import TelegramClient
    client = TelegramClient(
        "doornegar_session",
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    result = await client.send_code_request(PHONE)
    print(f"Code sent to {PHONE}")
    print(f"Phone code hash: {result.phone_code_hash}")
    print("Now run tg_auth_step2.py with your code")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

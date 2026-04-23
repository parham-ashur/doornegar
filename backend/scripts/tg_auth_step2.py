"""Step 2: Complete Telegram auth with code."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

PHONE = "+33760552000"
CODE = "52255"
HASH = "8186c4c707475de098"

async def main():
    from telethon import TelegramClient
    client = TelegramClient(
        "doornegar_session",
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    try:
        await client.sign_in(PHONE, CODE, phone_code_hash=HASH)
        print("Authentication successful!")
    except Exception as e:
        if "password" in str(e).lower() or "two" in str(e).lower():
            print(f"2FA is enabled. Error: {e}")
            await client.disconnect()
            return
        else:
            raise

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (ID: {me.id})")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

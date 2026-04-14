"""One-time Telegram authentication script.

Usage:
  Step 1: python scripts/telegram_auth.py --phone +33XXXXXXXXX
          (sends SMS code to your phone)

  Step 2: python scripts/telegram_auth.py --phone +33XXXXXXXXX --code 12345
          (completes authentication, creates session file)

After this, the session file persists and Telethon can connect automatically.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="Phone number with country code, e.g. +33612345678")
    parser.add_argument("--code", help="SMS verification code (step 2)")
    parser.add_argument("--password", help="2FA password if enabled")
    args = parser.parse_args()

    from telethon import TelegramClient

    client = TelegramClient(
        "doornegar_session",
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()

    if not args.code:
        # Step 1: send code
        result = await client.send_code_request(args.phone)
        print(f"Code sent to {args.phone}")
        print(f"Phone code hash: {result.phone_code_hash}")
        print(f"\nNow run again with: --code <YOUR_CODE>")
    else:
        # Step 2: sign in with code
        try:
            await client.sign_in(args.phone, args.code)
            print("Authentication successful!")
            print(f"Session file created: doornegar_session.session")
        except Exception as e:
            if "Two-step" in str(e) or "password" in str(e).lower():
                if args.password:
                    await client.sign_in(password=args.password)
                    print("Authentication successful (with 2FA)!")
                else:
                    print(f"2FA is enabled. Run again with --password YOUR_PASSWORD")
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

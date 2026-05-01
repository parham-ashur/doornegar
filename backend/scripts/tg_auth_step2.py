"""Step 2: Complete Telegram auth with the SMS code from step 1.

Usage:
    python scripts/tg_auth_step2.py <CODE> <PHONE_CODE_HASH>

Both values come from step 1's output. Don't paste them into the file —
hardcoded values get stale and silently fail (or worse, succeed with the
wrong identity).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

PHONE = "+33760552000"


async def main(code: str, phone_code_hash: str) -> int:
    from telethon import TelegramClient
    client = TelegramClient(
        "doornegar_session",
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "two-step" in msg or "twofactor" in msg or "2fa" in msg:
            print(f"2FA is enabled. Error: {e}", file=sys.stderr)
            print("This account has 2FA — Telethon needs the cloud password.", file=sys.stderr)
            await client.disconnect()
            return 2
        if "phone_code_expired" in msg or "phone_code_invalid" in msg:
            print(f"\nERROR: code expired or invalid: {e}", file=sys.stderr)
            print("Re-run tg_auth_step1.py to get a fresh code, then step2 with the new code+hash.", file=sys.stderr)
            await client.disconnect()
            return 1
        await client.disconnect()
        raise

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Authentication successful. Logged in as: {me.first_name} (id={me.id} username=@{getattr(me, 'username', '?')})")
        print()
        print("Next: python scripts/export_telegram_session.py")
    else:
        print("ERROR: sign_in returned but is_user_authorized=False — auth did not actually take.", file=sys.stderr)
        await client.disconnect()
        return 3
    await client.disconnect()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(64)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))

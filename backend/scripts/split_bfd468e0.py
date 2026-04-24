"""One-shot HITL split: carve bfd468e0 (534-article composite) into
four temporal chapters wrapped in a new arc. Calls the new
/hitl/stories/{id}/split endpoint end-to-end so the split logic is
tested on prod in the same transaction an admin UI would make.

Usage:
  railway run --service doornegar python scripts/split_bfd468e0.py --apply
"""
import argparse
import asyncio
import os

import httpx
from sqlalchemy import text

from app.database import async_session


SOURCE_ID = "bfd468e0-7383-471c-b7d3-e0c62b3ab509"

# Bucket boundaries (published_at or created_at, whichever exists).
# Each tuple: (title_fa, title_en, start_date_inclusive, end_date_exclusive)
CHAPTERS = [
    (
        "محاصرهٔ دریایی آمریکا و نخستین حملات؛ آغاز جنگ چهلم",
        "US naval blockade and first strikes",
        "2026-04-04",
        "2026-04-10",
    ),
    (
        "تشدید درگیری‌ها و زمینه‌چینی برای آتش‌بس",
        "Escalation and pre-ceasefire positioning",
        "2026-04-11",
        "2026-04-15",
    ),
    (
        "اعلام آتش‌بس و بازگشایی مشروط تنگهٔ هرمز",
        "Ceasefire announced; conditional Hormuz reopening",
        "2026-04-15",
        "2026-04-21",
    ),
    (
        "تمدید آتش‌بس و واکنش‌های بعد از توافق",
        "Ceasefire extension and post-agreement reactions",
        "2026-04-21",
        "2026-04-25",
    ),
]


async def fetch_article_ids(start: str, end: str) -> list[str]:
    from datetime import date

    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    async with async_session() as db:
        r = await db.execute(
            text(
                """
                SELECT id FROM articles
                WHERE story_id = :sid
                  AND COALESCE(published_at, created_at) >= :start
                  AND COALESCE(published_at, created_at) < :end
                """
            ),
            {"sid": SOURCE_ID, "start": start_d, "end": end_d},
        )
        return [str(row[0]) for row in r.all()]


async def main(apply: bool) -> None:
    groups = []
    for title_fa, title_en, start, end in CHAPTERS:
        ids = await fetch_article_ids(start, end)
        groups.append(
            {
                "title_fa": title_fa,
                "title_en": title_en,
                "article_ids": ids,
            }
        )
        print(f"[{start} → {end}] {len(ids):>4} articles — {title_fa[:50]}")

    total = sum(len(g["article_ids"]) for g in groups)
    print(f"\nTotal articles in groups: {total}")

    if not apply:
        print("\nDRY RUN — rerun with --apply to call the split endpoint.")
        return

    token = os.environ["ADMIN_TOKEN"]
    api = os.environ.get("API_BASE", "https://api.doornegar.org")
    payload = {
        "groups": groups,
        "arc_title_fa": "آتش‌بس ایران و آمریکا؛ از محاصرهٔ دریایی تا تمدید",
        "arc_slug": "iran-us-ceasefire-2026-04",
        "freeze_source": True,
    }

    url = f"{api}/api/v1/admin/hitl/stories/{SOURCE_ID}/split"
    print(f"\nPOST {url}")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    print(f"HTTP {r.status_code}")
    print(r.text[:1200])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.apply))

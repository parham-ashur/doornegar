"""One-shot scrub: remove side summaries for sides with zero articles.

Applies the same guard _enforce_side_presence runs at save time, but
retroactively against every story in the DB. Use once to clean up
historical niloofar_preliminary rows that predate the save-time gate.

Run against prod:
  railway run --service doornegar python scripts/scrub_hallucinated_sides.py
  railway run --service doornegar python scripts/scrub_hallucinated_sides.py --apply

Default is dry-run: prints which stories would be cleaned. Pass --apply
to commit.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(apply: bool) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database import async_session
    from app.models.article import Article
    from app.models.story import Story
    from app.services.narrative_groups import narrative_group, side_of

    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.summary_en.isnot(None))
        )
        stories = list(result.scalars().all())

        scanned = 0
        touched = 0
        cleared_counts: dict[str, int] = {}

        for story in stories:
            scanned += 1
            try:
                blob = json.loads(story.summary_en) if story.summary_en else {}
            except Exception:
                continue
            if not isinstance(blob, dict):
                continue

            inside = outside = independent = 0
            for a in story.articles:
                if not a.source:
                    continue
                if a.source.state_alignment == "independent":
                    independent += 1
                try:
                    grp = narrative_group(a.source)
                except Exception:
                    continue
                if side_of(grp) == "inside":
                    inside += 1
                else:
                    outside += 1

            cleared: list[str] = []
            if inside == 0:
                if blob.get("state_summary_fa"):
                    blob["state_summary_fa"] = None
                    cleared.append("state_summary_fa")
                nar = blob.get("narrative")
                if isinstance(nar, dict) and nar.get("inside"):
                    nar["inside"] = None
                    cleared.append("narrative.inside")
            if outside == 0:
                if blob.get("diaspora_summary_fa"):
                    blob["diaspora_summary_fa"] = None
                    cleared.append("diaspora_summary_fa")
                nar = blob.get("narrative")
                if isinstance(nar, dict) and nar.get("outside"):
                    nar["outside"] = None
                    cleared.append("narrative.outside")
            if independent == 0:
                if blob.get("independent_summary_fa"):
                    blob["independent_summary_fa"] = None
                    cleared.append("independent_summary_fa")

            if not cleared:
                continue

            touched += 1
            for k in cleared:
                cleared_counts[k] = cleared_counts.get(k, 0) + 1

            title = (story.title_fa or story.title_en or "")[:60]
            print(
                f"  [{touched}] {story.id}  inside={inside} outside={outside} independent={independent}"
                f"  cleared: {', '.join(cleared)}"
            )
            print(f"       {title}")

            if apply:
                story.summary_en = json.dumps(blob, ensure_ascii=False)

        if apply:
            await db.commit()
            print(f"\nApplied: {touched} stories cleaned of {scanned} scanned")
        else:
            print(f"\nDry run: {touched} stories would be cleaned of {scanned} scanned")
        if cleared_counts:
            print("Field-level totals:")
            for k, v in sorted(cleared_counts.items(), key=lambda kv: -kv[1]):
                print(f"  {k:>28}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    args = parser.parse_args()
    asyncio.run(main(args.apply))

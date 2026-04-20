"""
Neutrality audit — Claude-scored per-article neutrality.

The LLM pipeline no longer produces neutrality scores (saves tokens).
Instead the top-N trending stories are exported to JSON, a Claude
session reads the article text and returns per-article scores, and
--apply writes them back into each story's summary_en blob.

Usage:
  # 1. Export top-30 stories needing neutrality scoring
  python scripts/neutrality_audit.py --export /tmp/neut_in.json

  # 2. (In a Claude session) read neut_in.json, write neut_out.json
  #    with shape: [{"story_id": "...", "article_neutrality": {"<id>": -0.3, ...}}]

  # 3. Apply the scored file back to the DB
  python scripts/neutrality_audit.py --apply /tmp/neut_out.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.article import Article
from app.models.story import Story
from app.services.narrative_groups import narrative_group as _narrative_group
from app.services.story_analysis import _compute_article_evidence

ARTICLE_CONTENT_CAP = 3000  # per-article chars sent for review
SUBGROUP_FA = {
    "principlist": "اصول‌گرا",
    "reformist": "اصلاح‌طلب",
    "moderate_diaspora": "میانه‌رو",
    "radical_diaspora": "رادیکال",
}


async def export(top_n: int, out_path: str, include_scored: bool) -> None:
    async with async_session() as db:
        result = await db.execute(
            select(Story)
            .options(selectinload(Story.articles).selectinload(Article.source))
            .where(Story.summary_fa.isnot(None))
            .order_by(Story.trending_score.desc())
            .limit(top_n * 3)  # oversample — we filter after reading summary_en
        )
        stories = list(result.scalars().all())

        picked: list[dict] = []
        for s in stories:
            try:
                blob = json.loads(s.summary_en) if s.summary_en else {}
            except Exception:
                blob = {}
            if not include_scored and isinstance(blob, dict) and blob.get("article_neutrality"):
                continue

            arts_out = []
            for a in s.articles:
                if not a.source:
                    continue
                art_dict = {
                    "title": a.title_original or a.title_fa or a.title_en or "",
                    "content": (a.content_text or a.summary or "")[:ARTICLE_CONTENT_CAP],
                }
                evidence = _compute_article_evidence(art_dict)
                group = _narrative_group(a.source)
                arts_out.append({
                    "id": str(a.id),
                    "source_slug": a.source.slug,
                    "source_name_fa": a.source.name_fa,
                    "narrative_group": group,
                    "subgroup_fa": SUBGROUP_FA.get(group, "نامشخص"),
                    "published_at": a.published_at.isoformat() if a.published_at else None,
                    "title": art_dict["title"],
                    "content": art_dict["content"],
                    "evidence": evidence,
                })
            if not arts_out:
                continue
            picked.append({
                "story_id": str(s.id),
                "title_fa": s.title_fa,
                "article_count": len(arts_out),
                "articles": arts_out,
            })
            if len(picked) >= top_n:
                break

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(picked, f, ensure_ascii=False, indent=2)
        print(f"✓ exported {len(picked)} stories → {out_path}")


async def apply(in_path: str) -> None:
    with open(in_path, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise SystemExit("apply: expected a JSON array of {story_id, article_neutrality}")

    async with async_session() as db:
        updated = 0
        skipped = 0
        for entry in payload:
            sid = entry.get("story_id")
            scores_in = entry.get("article_neutrality") or {}
            if not sid or not isinstance(scores_in, dict) or not scores_in:
                skipped += 1
                continue

            # Clamp and coerce
            article_scores: dict[str, float] = {}
            for k, v in scores_in.items():
                try:
                    article_scores[str(k)] = max(-1.0, min(1.0, float(v)))
                except (TypeError, ValueError):
                    continue
            if not article_scores:
                skipped += 1
                continue

            res = await db.execute(
                select(Story)
                .options(selectinload(Story.articles).selectinload(Article.source))
                .where(Story.id == sid)
            )
            story = res.scalar_one_or_none()
            if not story:
                skipped += 1
                continue

            # Aggregate to per-source means
            per_source: dict[str, list[float]] = {}
            for a in story.articles:
                score = article_scores.get(str(a.id))
                if score is None or not a.source:
                    continue
                per_source.setdefault(a.source.slug, []).append(score)
            source_neutrality = {
                slug: sum(v) / len(v) for slug, v in per_source.items()
            }

            try:
                blob = json.loads(story.summary_en) if story.summary_en else {}
            except Exception:
                blob = {}
            if not isinstance(blob, dict):
                blob = {}

            blob["article_neutrality"] = article_scores
            blob["source_neutrality"] = source_neutrality
            blob["neutrality_source"] = "claude"
            blob["neutrality_scored_at"] = datetime.now(timezone.utc).isoformat()
            story.summary_en = json.dumps(blob, ensure_ascii=False)
            updated += 1

        await db.commit()
        print(f"✓ applied neutrality to {updated} stories (skipped {skipped})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--export", metavar="PATH", help="Export stories to JSON for Claude review")
    p.add_argument("--apply", metavar="PATH", help="Apply scored JSON back to DB")
    p.add_argument("--top", type=int, default=30, help="How many stories to export (default 30)")
    p.add_argument(
        "--include-scored", action="store_true",
        help="Re-export stories that already have neutrality (default: skip them)",
    )
    args = p.parse_args()

    if args.export:
        asyncio.run(export(args.top, args.export, args.include_scored))
    elif args.apply:
        asyncio.run(apply(args.apply))
    else:
        p.print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    main()

"""Compare clustering decisions under text-embedding-3-small (current
production) vs text-embedding-3-large.

For 500 recently-ingested articles and ~200 active stories:
1. Re-embed test articles + 3 anchor articles per story with BOTH
   models. For large we keep the full 3072 dims; for small we keep
   the production-equivalent 384 dims (Matryoshka truncation).
2. Build per-story centroid in each model (average of 3 anchors).
3. For each test article, compute cosine to every story centroid in
   both models. Take top-1.
4. A "divergent decision" is when small picks story A and large
   picks story B for the same article.
5. Output: aggregate stats + the 50 most-divergent cases (largest
   |small_score - large_score| gap on the disagreed-on stories) for
   manual labeling.

Read-only against the database. No writes.

Usage:
  cd backend && python scripts/embed_comparison.py [--n 500] [--anchors 200]

Cost at defaults: roughly $0.08 (mostly the large model embeds).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Make sure backend/ is on sys.path so `from app...` imports resolve
# whether this is invoked from backend/ or from the repo root.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.models.article import Article  # noqa: E402
from app.models.story import Story  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("embed_comparison")

SMALL_MODEL = "text-embedding-3-small"
SMALL_DIMS = 384  # matches production (Matryoshka truncation)
LARGE_MODEL = "text-embedding-3-large"
LARGE_DIMS = 3072  # full size

# Anchor strategy: pick this many member articles per story to define
# the per-story centroid in each model. Three is enough to average out
# noise without ballooning the embedding cost.
ANCHORS_PER_STORY = 3

# Don't ship more than this in one OpenAI call.
EMBED_BATCH_SIZE = 100

# Test pool — recent ingest window.
TEST_WINDOW_DAYS = 7

# Story pool — only consider stories that production's matcher would
# also accept (mirrors clustering.py F4 / umbrella caps).
STORY_RECENT_DAYS = 10
UMBRELLA_FIRST_PUB_DAYS = 14


def _truncate_for_embedding(text: str, max_chars: int = 8000) -> str:
    return (text or "").strip()[:max_chars]


def _representative_text(art: Article) -> str:
    """What we feed to the embedder. Title + content snippet, same
    shape used by the production NLP pipeline so our comparison
    reflects how the matcher actually sees these articles."""
    title = (art.title_original or art.title_fa or "").strip()
    body = (art.content_text or art.summary or "").strip()
    return _truncate_for_embedding(f"{title}\n\n{body}")


def _embed_batched(client, model: str, dims: int, texts: list[str]) -> list[list[float] | None]:
    """Synchronous batched embed call. Returns one vector per input
    text (None on failure). The OpenAI SDK is synchronous-blocking;
    we use it here in a thread executor for parallelism — see
    `asyncio.to_thread` below."""
    out: list[list[float] | None] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        try:
            resp = client.embeddings.create(
                model=model, input=batch, dimensions=dims
            )
        except Exception as e:
            log.warning("embed batch failed (model=%s start=%d): %s", model, start, e)
            out.extend([None] * len(batch))
            continue
        sorted_data = sorted(resp.data, key=lambda d: d.index)
        out.extend([d.embedding for d in sorted_data])
    return out


async def _embed_two_models(texts: list[str]) -> tuple[list[list[float] | None], list[list[float] | None]]:
    """Embed `texts` with both small and large models in parallel."""
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing — set it in backend/.env")

    client = OpenAI(api_key=settings.openai_api_key)

    small_task = asyncio.to_thread(
        _embed_batched, client, SMALL_MODEL, SMALL_DIMS, texts
    )
    large_task = asyncio.to_thread(
        _embed_batched, client, LARGE_MODEL, LARGE_DIMS, texts
    )
    small, large = await asyncio.gather(small_task, large_task)
    return small, large


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


def _build_centroid(vectors: list[list[float] | None]) -> list[float] | None:
    """Average of non-None vectors; None if all failed."""
    valid = [v for v in vectors if v is not None]
    if not valid:
        return None
    arr = np.array(valid, dtype=np.float32)
    return arr.mean(axis=0).tolist()


async def _load_test_articles(db: AsyncSession, n: int) -> list[Article]:
    """Pull the most recent N articles with non-empty body. We
    deliberately skip articles whose content_type was filtered out
    (those never went through clustering and have no opinion-on-story
    we'd want to compare)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=TEST_WINDOW_DAYS)
    result = await db.execute(
        select(Article)
        .where(
            Article.ingested_at >= cutoff,
            Article.content_text.isnot(None),
            (Article.content_type == "news") | (Article.content_type.is_(None)),
        )
        .order_by(Article.ingested_at.desc())
        .limit(n)
    )
    return list(result.scalars().all())


async def _load_anchor_stories(db: AsyncSession, n: int) -> list[Story]:
    """Active stories that production's matcher would also accept."""
    now = datetime.now(timezone.utc)
    last_updated_cutoff = now - timedelta(days=STORY_RECENT_DAYS)
    first_pub_cutoff = now - timedelta(days=UMBRELLA_FIRST_PUB_DAYS)
    result = await db.execute(
        select(Story)
        .where(
            Story.archived_at.is_(None),
            Story.last_updated_at >= last_updated_cutoff,
            (Story.first_published_at.is_(None))
            | (Story.first_published_at >= first_pub_cutoff),
            Story.article_count >= 2,
        )
        .order_by(Story.last_updated_at.desc())
        .limit(n)
    )
    return list(result.scalars().all())


async def _load_anchor_articles(
    db: AsyncSession, story_ids: list, per_story: int
) -> dict:
    """For each story, pull up to per_story most-recent member
    articles with non-empty body. Returns {story_id: [Article, ...]}."""
    if not story_ids:
        return {}
    out: dict = {sid: [] for sid in story_ids}
    result = await db.execute(
        select(Article)
        .where(
            Article.story_id.in_(story_ids),
            Article.content_text.isnot(None),
        )
        .order_by(Article.story_id, Article.published_at.desc().nullslast())
    )
    for art in result.scalars().all():
        bucket = out.get(art.story_id)
        if bucket is None:
            continue
        if len(bucket) < per_story:
            bucket.append(art)
    return out


async def main(n_articles: int, n_stories: int, out_path: Path) -> None:
    started = time.time()
    log.info(
        "Starting embed comparison: %d test articles, %d anchor stories",
        n_articles,
        n_stories,
    )

    async with async_session() as db:
        test_articles = await _load_test_articles(db, n_articles)
        log.info("Pulled %d test articles", len(test_articles))

        stories = await _load_anchor_stories(db, n_stories)
        log.info("Pulled %d candidate stories", len(stories))

        story_ids = [s.id for s in stories]
        anchors = await _load_anchor_articles(db, story_ids, ANCHORS_PER_STORY)

    # ── Step 1: embed test articles + anchor articles ──────────────────
    test_texts = [_representative_text(a) for a in test_articles]

    anchor_articles_flat: list[Article] = []
    anchor_to_story: list = []  # parallel list of story_ids
    for s in stories:
        for art in anchors.get(s.id, []):
            anchor_articles_flat.append(art)
            anchor_to_story.append(s.id)
    anchor_texts = [_representative_text(a) for a in anchor_articles_flat]

    log.info(
        "Embedding %d test + %d anchor texts × 2 models",
        len(test_texts),
        len(anchor_texts),
    )

    test_small, test_large = await _embed_two_models(test_texts)
    anchor_small, anchor_large = await _embed_two_models(anchor_texts)

    # ── Step 2: per-story centroids in each model ──────────────────────
    by_story_small: dict = {sid: [] for sid in story_ids}
    by_story_large: dict = {sid: [] for sid in story_ids}
    for sid, vec in zip(anchor_to_story, anchor_small):
        if vec is not None:
            by_story_small[sid].append(vec)
    for sid, vec in zip(anchor_to_story, anchor_large):
        if vec is not None:
            by_story_large[sid].append(vec)

    valid_story_ids = [
        sid
        for sid in story_ids
        if by_story_small[sid] and by_story_large[sid]
    ]
    log.info(
        "Built centroids for %d/%d stories (the rest had embedding failures)",
        len(valid_story_ids),
        len(story_ids),
    )
    if not valid_story_ids:
        log.error("No valid story centroids — aborting")
        return

    centroid_small = np.array(
        [_build_centroid(by_story_small[sid]) for sid in valid_story_ids],
        dtype=np.float32,
    )
    centroid_large = np.array(
        [_build_centroid(by_story_large[sid]) for sid in valid_story_ids],
        dtype=np.float32,
    )

    # Pre-normalize so cosine = dot product.
    centroid_small_n = _normalize(centroid_small)
    centroid_large_n = _normalize(centroid_large)

    story_lookup = {s.id: s for s in stories if s.id in valid_story_ids}

    # ── Step 3: top-1 match per article in each model ──────────────────
    rows: list[dict] = []
    for art, v_small, v_large in zip(test_articles, test_small, test_large):
        if v_small is None or v_large is None:
            continue
        a_small = _normalize(np.array([v_small], dtype=np.float32))[0]
        a_large = _normalize(np.array([v_large], dtype=np.float32))[0]

        sims_small = centroid_small_n @ a_small
        sims_large = centroid_large_n @ a_large

        i_small = int(np.argmax(sims_small))
        i_large = int(np.argmax(sims_large))
        score_small = float(sims_small[i_small])
        score_large = float(sims_large[i_large])

        rows.append({
            "article_id": str(art.id),
            "article_title": (art.title_original or art.title_fa or "")[:160],
            "article_body": (art.content_text or art.summary or "")[:500],
            "small_story_id": str(valid_story_ids[i_small]),
            "small_story_title": (story_lookup[valid_story_ids[i_small]].title_fa or "")[:160],
            "small_score": score_small,
            "large_story_id": str(valid_story_ids[i_large]),
            "large_story_title": (story_lookup[valid_story_ids[i_large]].title_fa or "")[:160],
            "large_score": score_large,
            "divergent": valid_story_ids[i_small] != valid_story_ids[i_large],
        })

    total = len(rows)
    divergent_rows = [r for r in rows if r["divergent"]]
    n_div = len(divergent_rows)
    pct = (100 * n_div / total) if total else 0
    log.info(
        "Top-1 divergence: %d / %d articles (%.1f%%)",
        n_div,
        total,
        pct,
    )

    # Rank divergences by combined-confidence proxy (avg of the two
    # competing scores) so the report leads with high-confidence
    # disagreements — those are the easiest to judge.
    divergent_rows.sort(
        key=lambda r: (r["small_score"] + r["large_score"]) / 2, reverse=True
    )
    sample = divergent_rows[:50]

    # ── Step 4: write report ───────────────────────────────────────────
    elapsed = time.time() - started
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Embedding model comparison — {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")
        fh.write(
            f"**Setup**: {SMALL_MODEL} @ {SMALL_DIMS} dims (production) vs "
            f"{LARGE_MODEL} @ {LARGE_DIMS} dims (proposed upgrade).\n\n"
        )
        fh.write(
            f"**Pool**: {len(test_articles)} test articles ingested in the last "
            f"{TEST_WINDOW_DAYS} days, {len(valid_story_ids)} candidate stories "
            f"(active in last {STORY_RECENT_DAYS}d, first-published within "
            f"{UMBRELLA_FIRST_PUB_DAYS}d, ≥2 articles).\n\n"
        )
        fh.write(f"**Centroid**: average of {ANCHORS_PER_STORY} most-recent member articles per story.\n\n")
        fh.write(f"**Runtime**: {elapsed:.1f}s\n\n")
        fh.write("## Headline numbers\n\n")
        fh.write(f"- Articles compared: **{total}**\n")
        fh.write(f"- Top-1 divergent decisions: **{n_div} ({pct:.1f}%)**\n")
        fh.write(f"- Same top-1: **{total - n_div} ({100 - pct:.1f}%)**\n\n")

        if sample:
            fh.write(f"## Top {len(sample)} divergent cases (highest combined confidence)\n\n")
            fh.write("For each: article on top, then the two competing story picks. "
                     "Add a verdict line manually after reading.\n\n")
            for i, r in enumerate(sample, 1):
                fh.write(f"### {i}. {r['article_title']}\n\n")
                fh.write(f"**Article body (first 500 chars)**:\n\n> {r['article_body']}\n\n")
                fh.write(f"- **small picks** → `{r['small_story_id'][:8]}` cosine={r['small_score']:.3f}\n")
                fh.write(f"  - {r['small_story_title']}\n")
                fh.write(f"- **large picks** → `{r['large_story_id'][:8]}` cosine={r['large_score']:.3f}\n")
                fh.write(f"  - {r['large_story_title']}\n\n")
                fh.write("**verdict**: ___ (small / large / tie / both wrong)\n\n---\n\n")

    log.info("Wrote report → %s", out_path)

    # Also dump structured data alongside the report for further analysis.
    json_path = out_path.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "small_model": SMALL_MODEL,
                "small_dims": SMALL_DIMS,
                "large_model": LARGE_MODEL,
                "large_dims": LARGE_DIMS,
                "anchors_per_story": ANCHORS_PER_STORY,
                "test_window_days": TEST_WINDOW_DAYS,
                "n_articles_compared": total,
                "n_divergent": n_div,
                "pct_divergent": pct,
                "rows": rows,
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )
    log.info("Wrote JSON → %s", json_path)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="number of test articles")
    ap.add_argument("--anchors", type=int, default=200, help="number of candidate stories")
    ap.add_argument(
        "--out",
        type=Path,
        default=BACKEND / "scripts" / f"embed_comparison_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.n, args.anchors, args.out))

"""Re-embed every article whose stored embedding is all zeros.

The silent zero-fill fallback in embeddings.py (now removed) left a
trail of zero-vector articles — up to 65% of the last 24h of ingest
and smaller fractions going back ~14 days. Until those are rewritten
with real vectors, the matcher cosine against them collapses to 0
and they keep dumping into cluster_new.

This script is idempotent. It only rewrites articles whose current
embedding is entirely zero, and only commits when the new vector
comes back non-zero — so any API hiccup during backfill doesn't
make things worse.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(apply: bool, batch_size: int, max_articles: int) -> None:
    from sqlalchemy import select, text as _text
    from app.database import async_session
    from app.models.article import Article
    from app.nlp.embeddings import generate_embeddings_batch
    from app.nlp.persian import extract_text_for_embedding, normalize

    async with async_session() as db:
        count_row = (await db.execute(_text(
            """
            SELECT count(*) AS n
            FROM articles
            WHERE embedding IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(embedding) v
                WHERE v::float <> 0
              )
            """
        ))).one()
        total_zero = count_row.n or 0
        print(f"articles with all-zero embeddings: {total_zero}")
        if not apply:
            print("dry run — pass --apply to re-embed")
            return
        if total_zero == 0:
            print("nothing to do")
            return

        ids_rows = (await db.execute(_text(
            f"""
            SELECT id
            FROM articles
            WHERE embedding IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(embedding) v
                WHERE v::float <> 0
              )
            ORDER BY ingested_at DESC
            LIMIT {int(max_articles)}
            """
        ))).all()
        target_ids = [r.id for r in ids_rows]
        print(f"processing up to {len(target_ids)} articles in batches of {batch_size}")

        total_written = 0
        total_skipped = 0

        for start in range(0, len(target_ids), batch_size):
            chunk_ids = target_ids[start:start + batch_size]
            rows = (await db.execute(
                select(Article).where(Article.id.in_(chunk_ids))
            )).scalars().all()

            texts = []
            kept = []
            for a in rows:
                title = a.title_original or a.title_fa or a.title_en or ""
                body = a.content_text or a.summary or ""
                try:
                    txt = extract_text_for_embedding(title, body)
                except Exception:
                    txt = f"{title} {body}"[:4000]
                if not (txt or "").strip():
                    total_skipped += 1
                    continue
                texts.append(txt)
                kept.append(a)

            if not texts:
                continue

            embeddings = await asyncio.to_thread(
                generate_embeddings_batch, texts, batch_size
            )

            written_this_chunk = 0
            for a, emb in zip(kept, embeddings):
                if emb is None:
                    total_skipped += 1
                    continue
                if not any(v != 0.0 for v in emb[:10]):
                    total_skipped += 1
                    continue
                a.embedding = emb
                written_this_chunk += 1

            await db.commit()
            total_written += written_this_chunk
            print(
                f"  batch {start // batch_size + 1}: wrote {written_this_chunk}/{len(kept)} "
                f"(cumulative written={total_written}, skipped={total_skipped})"
            )

        print(f"\nDone. wrote={total_written}  skipped={total_skipped}  target={len(target_ids)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max", type=int, default=10000, help="hard cap on articles processed")
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.batch_size, args.max))

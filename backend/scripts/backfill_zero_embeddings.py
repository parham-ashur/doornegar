"""Re-embed every article whose stored embedding is all zeros.

The silent zero-fill fallback in embeddings.py (now removed) left a
trail of zero-vector articles — up to 65% of the last 24h of ingest
and smaller fractions going back ~14 days. Until those are rewritten
with real vectors, the matcher cosine against them collapses to 0
and they keep dumping into cluster_new.

Connection discipline:
  Each batch opens a short-lived session *around the commit only*.
  The OpenAI embedding phase runs OUTSIDE any open DB session, so
  Neon's ~5-minute idle timeout cannot kill the connection mid-work.
  Prints are flushed so Railway log tails show progress live.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


async def main(apply: bool, batch_size: int, max_articles: int) -> None:
    from sqlalchemy import select, update, text as _text
    from app.database import async_session
    from app.models.article import Article
    from app.nlp.embeddings import generate_embeddings_batch
    from app.nlp.persian import extract_text_for_embedding

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
        _print(f"articles with all-zero embeddings: {total_zero}")
        if not apply:
            _print("dry run — pass --apply to re-embed")
            return
        if total_zero == 0:
            _print("nothing to do")
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
    # session closed — embedding phase is DB-free

    _print(f"processing up to {len(target_ids)} articles in batches of {batch_size}")

    total_written = 0
    total_skipped = 0

    for start in range(0, len(target_ids), batch_size):
        chunk_ids = target_ids[start:start + batch_size]

        # --- Short read session: load texts only, then close ---
        async with async_session() as db:
            rows = (await db.execute(
                select(
                    Article.id,
                    Article.title_original, Article.title_fa, Article.title_en,
                    Article.content_text, Article.summary,
                ).where(Article.id.in_(chunk_ids))
            )).all()

        texts: list[str] = []
        kept_ids: list = []
        for r in rows:
            title = r.title_original or r.title_fa or r.title_en or ""
            body = r.content_text or r.summary or ""
            try:
                txt = extract_text_for_embedding(title, body)
            except Exception:
                txt = f"{title} {body}"[:4000]
            if not (txt or "").strip():
                total_skipped += 1
                continue
            texts.append(txt)
            kept_ids.append(r.id)

        if not texts:
            _print(f"  batch {start // batch_size + 1}: no usable text, skipped {len(rows)}")
            continue

        # --- Embedding phase: no DB session open ---
        embeddings = await asyncio.to_thread(
            generate_embeddings_batch, texts, batch_size
        )

        # --- Short write session: per-row UPDATE + commit ---
        async with async_session() as db:
            written = 0
            for aid, emb in zip(kept_ids, embeddings):
                if emb is None or not any(v != 0.0 for v in emb[:10]):
                    total_skipped += 1
                    continue
                await db.execute(
                    update(Article).where(Article.id == aid).values(embedding=emb)
                )
                written += 1
            await db.commit()
        total_written += written
        _print(
            f"  batch {start // batch_size + 1}/{(len(target_ids) + batch_size - 1) // batch_size}: "
            f"wrote {written}  cumulative_written={total_written}  skipped={total_skipped}"
        )

    _print(f"\nDone. wrote={total_written}  skipped={total_skipped}  target={len(target_ids)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max", type=int, default=10000, help="hard cap on articles processed")
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.batch_size, args.max))

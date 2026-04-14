"""Link Telegram posts to stories via embedding similarity, then run deep analysis."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SIMILARITY_THRESHOLD = 0.35  # minimum cosine similarity to link


async def main():
    from app.database import async_session
    from app.nlp.embeddings import generate_embeddings_batch, cosine_similarity
    from app.models.social import TelegramPost
    from app.models.story import Story
    from app.services.telegram_analysis import analyze_story_telegram
    from sqlalchemy import select, func

    # ── Step 1: Load stories with centroids ──
    print("=== Step 1: Loading story centroids ===")
    async with async_session() as db:
        result = await db.execute(
            select(Story).where(
                Story.centroid_embedding.isnot(None),
                Story.article_count >= 3,
            )
        )
        stories = list(result.scalars().all())
        print(f"  {len(stories)} stories with centroids")

        story_data = [(str(s.id), s.title_fa or "", s.centroid_embedding) for s in stories]

    # ── Step 2: Get unlinked posts with text ──
    print("\n=== Step 2: Loading unlinked posts ===")
    async with async_session() as db:
        result = await db.execute(
            select(TelegramPost).where(
                TelegramPost.story_id.is_(None),
                TelegramPost.text.isnot(None),
                TelegramPost.text != "",
            )
        )
        posts = list(result.scalars().all())
        print(f"  {len(posts)} unlinked posts with text")

    if not posts or not story_data:
        print("Nothing to link")
        return

    # ── Step 3: Embed posts in batches ──
    print("\n=== Step 3: Generating embeddings for posts ===")
    post_texts = []
    for p in posts:
        text = (p.text or "")[:500]  # truncate for embedding
        post_texts.append(text)

    embeddings = generate_embeddings_batch(post_texts, batch_size=100)
    print(f"  Generated {len(embeddings)} embeddings")

    # ── Step 4: Match posts to stories ──
    print("\n=== Step 4: Matching posts to stories ===")
    matches = []  # (post_id, story_id, score)
    for i, (post, emb) in enumerate(zip(posts, embeddings)):
        if not emb or all(v == 0 for v in emb):
            continue

        best_score = 0
        best_story_id = None
        for story_id, story_title, centroid in story_data:
            if not centroid:
                continue
            score = cosine_similarity(emb, centroid)
            if score > best_score:
                best_score = score
                best_story_id = story_id

        if best_score >= SIMILARITY_THRESHOLD and best_story_id:
            matches.append((post.id, best_story_id, best_score))

        if (i + 1) % 200 == 0:
            print(f"  Processed {i + 1}/{len(posts)}...")

    print(f"  {len(matches)} posts matched (threshold: {SIMILARITY_THRESHOLD})")

    # ── Step 5: Update DB ──
    print("\n=== Step 5: Saving links to DB ===")
    async with async_session() as db:
        from sqlalchemy import update
        for post_id, story_id, score in matches:
            await db.execute(
                update(TelegramPost)
                .where(TelegramPost.id == post_id)
                .values(story_id=story_id)
            )
        await db.commit()
        print(f"  Linked {len(matches)} posts")

        # Check distribution
        result = await db.execute(
            select(Story.title_fa, func.count(TelegramPost.id).label("pc"))
            .join(TelegramPost, TelegramPost.story_id == Story.id)
            .where(TelegramPost.text.isnot(None))
            .group_by(Story.id, Story.title_fa)
            .having(func.count(TelegramPost.id) >= 2)
            .order_by(func.count(TelegramPost.id).desc())
            .limit(15)
        )
        rows = result.all()
        print(f"\n  Stories with 2+ posts ({len(rows)}):")
        for title, count in rows:
            print(f"    {count} posts: {(title or '')[:55]}")

    # ── Step 6: Run deep analysis ──
    print("\n=== Step 6: Running deep Telegram analysis ===")
    async with async_session() as db:
        result = await db.execute(
            select(Story.id, Story.title_fa)
            .join(TelegramPost, TelegramPost.story_id == Story.id)
            .where(TelegramPost.text.isnot(None))
            .group_by(Story.id, Story.title_fa)
            .having(func.count(TelegramPost.id) >= 2)
            .order_by(func.count(TelegramPost.id).desc())
            .limit(15)
        )
        stories_to_analyze = result.all()

        analyzed = 0
        for sid, title in stories_to_analyze:
            print(f"  Analyzing: {(title or '')[:50]}...")
            try:
                analysis = await analyze_story_telegram(db, str(sid))
                if analysis:
                    analyzed += 1
                    print(f"    ✓ {analysis.get('discourse_summary', '')[:60]}")
                else:
                    print("    - skipped")
            except Exception as e:
                print(f"    ✗ {e}")

        print(f"\n=== Done! {analyzed} stories analyzed ===")


if __name__ == "__main__":
    asyncio.run(main())

-- ============================================================
-- DOORNEGAR CLEAN SLATE — 2026-05-12
-- ============================================================
-- Policy (Parham 2026-05-12):
--   KEEP: stories currently on homepage (top-30 trending + top-20
--         blindspots) PLUS stories <7 days old (grace period)
--   DELETE: everything else (stories >7d not on homepage + their
--           articles + their bias_scores + their analyst_takes +
--           their story_events + telegram_posts >7d)
--
-- Run in Neon SQL Editor. Steps are transactional — COMMIT only
-- after final counts look right. ROLLBACK at any time before
-- COMMIT to abort cleanly.
--
-- IMPORTANT: verify R2 backup is current before COMMIT. The
-- transaction can be rolled back, but COMMIT is permanent.
-- ============================================================

BEGIN;

-- ============================================================
-- Step 1: identify keep set
-- ============================================================

CREATE TEMP TABLE keep_stories AS
WITH trending_keep AS (
  SELECT id FROM stories
  WHERE archived_at IS NULL
    AND article_count >= 4
    AND trending_score > 0.5
    AND is_blindspot = false
  ORDER BY priority DESC, trending_score DESC
  LIMIT 30
),
blindspots_keep AS (
  SELECT id FROM stories
  WHERE archived_at IS NULL
    AND article_count >= 4
    AND is_blindspot = true
    AND last_updated_at >= NOW() - INTERVAL '14 days'
  ORDER BY first_published_at DESC
  LIMIT 20
),
grace_keep AS (
  -- Recently published stories still ramping up; protected from
  -- deletion for 7 days so they have a chance to reach homepage.
  SELECT id FROM stories
  WHERE first_published_at >= NOW() - INTERVAL '7 days'
)
SELECT id FROM trending_keep
UNION SELECT id FROM blindspots_keep
UNION SELECT id FROM grace_keep;

CREATE INDEX ON keep_stories (id);

CREATE TEMP TABLE keep_articles AS
SELECT a.id FROM articles a
WHERE a.story_id IN (SELECT id FROM keep_stories);

CREATE INDEX ON keep_articles (id);

-- ============================================================
-- Preview: how many of each will we keep / delete?
-- ============================================================

SELECT 'KEEP: stories' AS bucket, COUNT(*) AS rows FROM keep_stories
UNION ALL
SELECT 'KEEP: articles', COUNT(*) FROM keep_articles
UNION ALL
SELECT 'DELETE: stories', COUNT(*) FROM stories WHERE id NOT IN (SELECT id FROM keep_stories)
UNION ALL
SELECT 'DELETE: articles', COUNT(*) FROM articles WHERE id NOT IN (SELECT id FROM keep_articles)
UNION ALL
SELECT 'DELETE: telegram_posts >7d', COUNT(*) FROM telegram_posts WHERE created_at < NOW() - INTERVAL '7 days';

-- ============================================================
-- Step 2: cascade deletes in FK-safe order
-- ============================================================

-- 2a. bias_scores (FK → articles)
DELETE FROM bias_scores
WHERE article_id NOT IN (SELECT id FROM keep_articles);

-- 2b. community_ratings (FK → articles, maybe stories)
DELETE FROM community_ratings
WHERE (article_id IS NOT NULL AND article_id NOT IN (SELECT id FROM keep_articles));

-- 2c. story_events (FK → stories)
DELETE FROM story_events
WHERE story_id NOT IN (SELECT id FROM keep_stories);

-- 2d. analyst_takes (FK → stories)
DELETE FROM analyst_takes
WHERE story_id NOT IN (SELECT id FROM keep_stories);

-- 2e. improvement_feedback uses `orphaned_from_story_id` (not story_id)
-- and tracks user feedback about specific stories that may already be
-- gone. Leave it alone — small table, not bot-walked, no FK to stories.

-- 2f. (skipped — `ratings` doesn't exist as a separate table; the
-- only ratings table is `community_ratings`, handled in step 2b.)

-- 2g. telegram_posts: NULL out story_id pointing at to-be-deleted
-- stories. Keep posts ≤7d regardless of their story link.
UPDATE telegram_posts
SET story_id = NULL
WHERE story_id IS NOT NULL AND story_id NOT IN (SELECT id FROM keep_stories);

-- 2h. Delete telegram_posts >7 days old (matches 7-day data window).
DELETE FROM telegram_posts
WHERE created_at < NOW() - INTERVAL '7 days';

-- 2i. articles for non-kept stories OR orphans
DELETE FROM articles
WHERE id NOT IN (SELECT id FROM keep_articles);

-- 2j. stories — last so all dependent rows are gone
DELETE FROM stories
WHERE id NOT IN (SELECT id FROM keep_stories);

-- ============================================================
-- Step 3: final verification
-- ============================================================

SELECT 'FINAL: stories' AS t, COUNT(*) AS rows FROM stories
UNION ALL
SELECT 'FINAL: articles', COUNT(*) FROM articles
UNION ALL
SELECT 'FINAL: telegram_posts', COUNT(*) FROM telegram_posts
UNION ALL
SELECT 'FINAL: bias_scores', COUNT(*) FROM bias_scores
UNION ALL
SELECT 'FINAL: community_ratings', COUNT(*) FROM community_ratings
UNION ALL
SELECT 'FINAL: story_events', COUNT(*) FROM story_events
UNION ALL
SELECT 'FINAL: analyst_takes', COUNT(*) FROM analyst_takes;

-- ============================================================
-- COMMIT or ROLLBACK
-- ============================================================
-- Expected post-counts:
--   stories          ~99 (50 homepage + 49 grace)
--   articles         ~7,288
--   telegram_posts   ~10,650
--   bias_scores      ~small (only for kept articles)
--   community_ratings ~small
--   story_events     ~small (only for kept stories)
--   analyst_takes    ~small (only for kept stories)
--
-- If those match expectations → COMMIT;
-- If anything looks wrong   → ROLLBACK;

-- Uncomment ONE of these AFTER reviewing the FINAL counts above:
-- COMMIT;
-- ROLLBACK;


-- ============================================================
-- Step 4: AFTER COMMIT only — reclaim disk space
-- ============================================================
-- VACUUM FULL cannot run inside a transaction. Run these AS SEPARATE
-- queries in Neon SQL Editor AFTER you've committed the deletes above.
-- Each takes a brief table lock; tables small enough for fast runs.
--
-- VACUUM FULL stories;
-- VACUUM FULL articles;
-- VACUUM FULL telegram_posts;
-- VACUUM FULL bias_scores;
-- VACUUM FULL story_events;
-- VACUUM FULL analyst_takes;

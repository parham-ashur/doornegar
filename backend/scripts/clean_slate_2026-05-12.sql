-- ============================================================
-- DOORNEGAR CLEAN SLATE — 2026-05-12 (EXECUTED)
-- ============================================================
-- Policy (Parham 2026-05-12):
--   KEEP: stories currently on homepage (top-30 trending + top-20
--         blindspots) PLUS stories <7 days old (grace period)
--   DELETE: everything else (stories >7d not on homepage + their
--           articles + their bias_scores + their analyst_takes +
--           their story_events + their social_sentiment_snapshots +
--           telegram_posts >7d)
--
-- Executed 2026-05-12: deleted 1491 stories, 25061 articles,
-- 42070 telegram posts, plus dependent rows. Resulting DB:
-- 99 stories, 7288 articles, 10650 telegram posts.
--
-- Run in Neon SQL Editor. Steps are transactional — COMMIT only
-- after final counts look right. ROLLBACK at any time before
-- COMMIT to abort cleanly.
-- ============================================================

BEGIN;

CREATE TEMP TABLE keep_stories AS
WITH trending_keep AS (
  SELECT id FROM stories
  WHERE archived_at IS NULL AND article_count >= 4
    AND trending_score > 0.5 AND is_blindspot = false
  ORDER BY priority DESC, trending_score DESC LIMIT 30
),
blindspots_keep AS (
  SELECT id FROM stories
  WHERE archived_at IS NULL AND article_count >= 4
    AND is_blindspot = true
    AND last_updated_at >= NOW() - INTERVAL '14 days'
  ORDER BY first_published_at DESC LIMIT 20
),
grace_keep AS (
  SELECT id FROM stories WHERE first_published_at >= NOW() - INTERVAL '7 days'
)
SELECT id FROM trending_keep
UNION SELECT id FROM blindspots_keep
UNION SELECT id FROM grace_keep;
CREATE INDEX ON keep_stories (id);

CREATE TEMP TABLE keep_articles AS
SELECT a.id FROM articles a WHERE a.story_id IN (SELECT id FROM keep_stories);
CREATE INDEX ON keep_articles (id);

CREATE TEMP TABLE delete_tg_posts AS
SELECT id FROM telegram_posts WHERE created_at < NOW() - INTERVAL '7 days';
CREATE INDEX ON delete_tg_posts (id);

-- FK cleanup phase: NULL nullable refs that would dangle
UPDATE rater_feedback SET article_id = NULL
WHERE article_id IS NOT NULL AND article_id NOT IN (SELECT id FROM keep_articles);
UPDATE rater_feedback SET story_id = NULL
WHERE story_id IS NOT NULL AND story_id NOT IN (SELECT id FROM keep_stories);

-- Article-FK dependents
DELETE FROM bias_scores WHERE article_id NOT IN (SELECT id FROM keep_articles);
DELETE FROM community_ratings WHERE article_id IS NOT NULL AND article_id NOT IN (SELECT id FROM keep_articles);

-- Story-FK dependents (NOT NULL constraints — must DELETE not NULL)
DELETE FROM social_sentiment_snapshots WHERE story_id NOT IN (SELECT id FROM keep_stories);
DELETE FROM story_events WHERE story_id NOT IN (SELECT id FROM keep_stories);

-- analyst_takes.telegram_post_id → telegram_posts (nullable, but
-- must NULL before deleting telegram_posts to avoid FK violation)
UPDATE analyst_takes SET telegram_post_id = NULL
WHERE telegram_post_id IN (SELECT id FROM delete_tg_posts);
DELETE FROM analyst_takes WHERE story_id NOT IN (SELECT id FROM keep_stories);

-- telegram_posts: NULL story_id for to-be-deleted stories, then drop >7d
UPDATE telegram_posts SET story_id = NULL
WHERE story_id IS NOT NULL AND story_id NOT IN (SELECT id FROM keep_stories);
DELETE FROM telegram_posts WHERE id IN (SELECT id FROM delete_tg_posts);

-- Finally, the parent rows
DELETE FROM articles WHERE id NOT IN (SELECT id FROM keep_articles);
DELETE FROM stories WHERE id NOT IN (SELECT id FROM keep_stories);

-- Verification
SELECT 'stories' AS t, COUNT(*) AS rows FROM stories
UNION ALL SELECT 'articles', COUNT(*) FROM articles
UNION ALL SELECT 'telegram_posts', COUNT(*) FROM telegram_posts
UNION ALL SELECT 'bias_scores', COUNT(*) FROM bias_scores
UNION ALL SELECT 'community_ratings', COUNT(*) FROM community_ratings
UNION ALL SELECT 'story_events', COUNT(*) FROM story_events
UNION ALL SELECT 'analyst_takes', COUNT(*) FROM analyst_takes
UNION ALL SELECT 'social_sentiment_snapshots', COUNT(*) FROM social_sentiment_snapshots;

-- Review the FINAL counts. If they look right:
-- COMMIT;
-- Else:
-- ROLLBACK;

-- After COMMIT only (cannot run inside transaction):
-- VACUUM FULL stories;
-- VACUUM FULL articles;
-- VACUUM FULL telegram_posts;
-- VACUUM FULL bias_scores;
-- VACUUM FULL story_events;
-- VACUUM FULL analyst_takes;

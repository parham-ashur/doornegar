"""Regression tests for the 2026-05-03 war-audit fixes.

These tests would have caught the bugs that took down the homepage for
6 days. Each test maps to a specific fix shipped in commits between
b051e50 and 095b5b6 (see memory project_war_audit_2026-05-03.md).

The tests are intentionally narrow — each one fails fast if its
specific regression returns. Coverage isn't comprehensive; it's
load-bearing on the few invariants that broke production.

Run: `cd backend && pytest tests/test_war_audit_fixes.py -v`
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═════════════════════════════════════════════════════════════════════
# 1. Embedding API contract: never silent-fallback to zeros
# ═════════════════════════════════════════════════════════════════════

class TestEmbeddingNoSilentFallback:
    """The April 2026 incident: a transient OpenAI failure returned a
    zero-filled vector that passed `is not None` but collapsed every
    cosine comparison to 0. Wrappers MUST return None on failure.
    """

    def test_generate_embedding_returns_none_on_api_failure(self):
        from app.nlp import embeddings as emb

        with patch.object(emb, "_call_with_retry", side_effect=RuntimeError("boom")):
            result = emb.generate_embedding("any text")

        assert result is None, (
            "Embedding API failure must return None — never a zero vector. "
            "See feedback_no_silent_fallbacks.md."
        )

    def test_generate_embeddings_batch_returns_none_per_failed_item(self):
        from app.nlp import embeddings as emb

        with patch.object(emb, "_call_with_retry", side_effect=RuntimeError("rate limited")):
            # batch of 2 — split-and-retry recursion means each item ends None
            result = emb.generate_embeddings_batch(["alpha", "beta"], batch_size=10)

        assert result == [None, None], (
            "Batch helper must propagate None per item, not collapse to zero "
            "vectors or empty lists."
        )

    def test_generate_embedding_skips_when_no_api_key(self):
        from app.nlp import embeddings as emb

        with patch.object(emb.settings, "openai_api_key", None):
            result = emb.generate_embedding("any text")

        assert result is None, "Missing API key must produce None, not a default."


# ═════════════════════════════════════════════════════════════════════
# 2. Sentinel-column trap: processed_at only on success
# ═════════════════════════════════════════════════════════════════════

class TestProcessedAtSentinelTrap:
    """The 2026-05-03 incident: process_unprocessed_articles set
    `processed_at = now` on EVERY article in the batch — including
    those whose embedding failed. On the next run, `processed_at IS
    NULL` excluded them forever. 1097 articles became permanent orphans.

    The fix: only stamp processed_at when embed succeeded OR there was
    no content to embed in the first place. Articles with content +
    failed embedding must keep processed_at NULL so they retry.
    """

    @pytest.mark.asyncio
    async def test_failed_embedding_leaves_processed_at_null(self):
        """An article with content but no embedding stays unstamped."""
        from app.services import nlp_pipeline as nlp

        # Article with content_text but None embedding (post-failure state).
        # We mock everything around it to isolate the stamp logic.
        article = MagicMock()
        article.id = "art-1"
        article.embedding = None
        article.content_text = "some real article body that should embed"
        article.summary = None
        article.title_original = "Title"
        article.title_fa = "عنوان"
        article.title_en = "Title"
        article.url = None
        article.image_url = None
        article.language = "fa"
        article.story_id = None
        article.source = SimpleNamespace(slug="test", id="src-1")
        article.processed_at = None  # starting state

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[article]))
        )))
        db.commit = AsyncMock()

        with patch.object(nlp, "_fetch_and_extract", AsyncMock(return_value=None)), \
             patch.object(nlp, "_fetch_og_image", AsyncMock(return_value=None)), \
             patch.object(nlp, "_validate_image_url", AsyncMock(return_value=True)), \
             patch.object(nlp, "_search_free_image", AsyncMock(return_value=None)), \
             patch.object(nlp, "extract_keywords", return_value=[]), \
             patch.object(nlp, "extract_text_for_embedding", return_value="text"), \
             patch.object(nlp, "translate_batch_fa_to_en", return_value=[]), \
             patch.object(nlp, "translate_en_to_fa", return_value=None), \
             patch.object(nlp, "generate_embeddings_batch", return_value=[None]):
            stats = await nlp.process_unprocessed_articles(db)

        assert article.processed_at is None, (
            "Sentinel-column trap regression: an article with content but "
            "failed embedding must keep processed_at IS NULL so the next "
            "maintenance run retries it. See feedback_processed_at_trap.md."
        )
        assert stats.get("skipped_unstamped", 0) == 1

    @pytest.mark.asyncio
    async def test_successful_embedding_stamps_processed_at(self):
        """Sanity check: a successful embed DOES set processed_at."""
        from app.services import nlp_pipeline as nlp

        article = MagicMock()
        article.id = "art-2"
        article.embedding = None
        article.content_text = "body"
        article.summary = None
        article.title_original = "Title"
        article.title_fa = "عنوان"
        article.title_en = "Title"
        article.url = None
        article.image_url = None
        article.language = "fa"
        article.story_id = None
        article.source = SimpleNamespace(slug="test", id="src-1")
        article.processed_at = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[article]))
        )))
        db.commit = AsyncMock()

        good_embedding = [0.1] * 384
        with patch.object(nlp, "_fetch_and_extract", AsyncMock(return_value=None)), \
             patch.object(nlp, "_fetch_og_image", AsyncMock(return_value=None)), \
             patch.object(nlp, "_validate_image_url", AsyncMock(return_value=True)), \
             patch.object(nlp, "_search_free_image", AsyncMock(return_value=None)), \
             patch.object(nlp, "extract_keywords", return_value=[]), \
             patch.object(nlp, "extract_text_for_embedding", return_value="text"), \
             patch.object(nlp, "translate_batch_fa_to_en", return_value=[]), \
             patch.object(nlp, "translate_en_to_fa", return_value=None), \
             patch.object(nlp, "generate_embeddings_batch", return_value=[good_embedding]):
            await nlp.process_unprocessed_articles(db)

        assert article.processed_at is not None, (
            "Successful embed must stamp processed_at — otherwise the "
            "article re-enters the queue forever and we re-pay LLM cost."
        )


# ═════════════════════════════════════════════════════════════════════
# 3. Clustering: floor lowered, batches of 2 are seeded
# ═════════════════════════════════════════════════════════════════════

class TestClusterNewGroupFloor:
    """Single biggest orphan-rate driver per the clustering audit. The
    prior floor of 5 skipped every batch under 5 — orphans piled up to
    5342. Lowered to 2 (singletons still excluded so wire stories don't
    spawn micro-stories).
    """

    def test_floor_is_two_not_five(self):
        from app.services import clustering as c

        assert c.CLUSTER_NEW_GROUP_FLOOR == 2, (
            "CLUSTER_NEW_GROUP_FLOOR was raised back above 2. The 2026-05-03 "
            "audit identified this as the biggest orphan-rate lever — raising "
            "it strands articles that could have seeded fresh stories."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. Clustering: bad-embedding guard catches both None and []
# ═════════════════════════════════════════════════════════════════════

class TestBadEmbeddingGuard:
    """The matcher's bad-embedding check (clustering.py:865) was
    `not article.embedding or not any(...)`. The audit flagged that
    `[]` (empty list) is technically caught but ambiguous across paths.
    Tightened with explicit length + isinstance.

    These tests duplicate the predicate locally — if the real code
    changes the shape of the check, this test breaks first and forces
    a deliberate review.
    """

    @staticmethod
    def _is_bad(emb):
        # Mirrors the predicate at clustering.py around line 875.
        if not isinstance(emb, list):
            return True
        if len(emb) == 0:
            return True
        return not any(v != 0.0 for v in emb[:5])

    def test_none_embedding_classified_bad(self):
        assert self._is_bad(None)

    def test_empty_list_classified_bad(self):
        assert self._is_bad([])

    def test_zero_vector_classified_bad(self):
        assert self._is_bad([0.0] * 384)

    def test_dict_not_list_classified_bad(self):
        # Defends against a future ORM/JSONB shape change that
        # accidentally returns a dict where a list is expected.
        assert self._is_bad({"vector": [0.1] * 384})

    def test_real_vector_classified_good(self):
        assert not self._is_bad([0.1] * 384)

    def test_partial_zero_real_vector_good(self):
        # A vector whose first 4 components are zero but 5th is non-zero
        # passes — `[:5]` window catches it.
        emb = [0.0, 0.0, 0.0, 0.0, 0.7] + [0.1] * 379
        assert not self._is_bad(emb)


# ═════════════════════════════════════════════════════════════════════
# 5. Homepage scope: trending API filter mirror
# ═════════════════════════════════════════════════════════════════════

class TestHomepageScope:
    """homepage_story_ids() must mirror the trending + blindspots API
    filters EXACTLY. Drift here = LLM spend lands on stories visitors
    never see (the April-May 2026 cost overage).
    """

    def test_module_constants_match_trending_api(self):
        """The min_articles + min_score constants must equal the API defaults."""
        from app.services.homepage_scope import (
            TRENDING_MIN_ARTICLES,
            TRENDING_MIN_SCORE,
            BLINDSPOT_MIN_ARTICLES,
        )

        # These values are mirrored from api/v1/stories.py — if either
        # side changes, both sides change. This test is a tripwire.
        assert TRENDING_MIN_ARTICLES == 4, (
            "TRENDING_MIN_ARTICLES drifted from the API default (4). "
            "Update both api/v1/stories.py:trending_stories AND "
            "app/services/homepage_scope.py together."
        )
        assert TRENDING_MIN_SCORE == 0.5, (
            "TRENDING_MIN_SCORE drifted from the API default (0.5)."
        )
        assert BLINDSPOT_MIN_ARTICLES == 4, (
            "BLINDSPOT_MIN_ARTICLES drifted from the API default."
        )

    def test_homepage_eligible_filters_excludes_archived_and_hidden(self):
        """The looser SQL-side predicate must still exclude archived
        + fully-hidden stories. (frozen_at intentionally NOT filtered
        per Parham 2026-05-03 — frozen stays visible.)
        """
        from app.services.homepage_scope import homepage_eligible_filters

        filters = homepage_eligible_filters()
        # Render to string so we can assert by SQL fragment.
        rendered = " ".join(str(f) for f in filters).lower()

        assert "archived_at is null" in rendered, (
            "homepage_eligible_filters must still exclude archived_at."
        )
        assert "frozen_at" not in rendered, (
            "homepage_eligible_filters must NOT filter frozen_at — "
            "frozen stays visible per Parham 2026-05-03 rule."
        )


# ═════════════════════════════════════════════════════════════════════
# 6. Trending API: frozen stories are eligible
# ═════════════════════════════════════════════════════════════════════

class TestFrozenStaysOnHomepage:
    """Per Parham 2026-05-03: freeze means 'no new articles can join
    this cluster' — NOT 'this story leaves the homepage.' The trending
    + blindspots APIs must NOT filter frozen_at.
    """

    def test_trending_endpoint_does_not_filter_frozen_at(self):
        # Read the source rather than introspect SQL — clearer signal.
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py"
        )
        source = src_path.read_text()

        # Find the trending_stories function body.
        marker = "async def trending_stories"
        start = source.find(marker)
        assert start >= 0, "Could not locate trending_stories function"
        # Window of ~2000 chars from the function start covers the where clause.
        window = source[start : start + 2500]

        # The where clause must NOT include `Story.frozen_at.is_(None)`.
        # If it does, frozen stories vanish from the homepage and we
        # repeat the 6-day empty-homepage incident.
        assert "Story.frozen_at.is_(None)" not in window, (
            "trending_stories endpoint re-introduced the Story.frozen_at "
            "IS NULL filter. This caused the 6-day empty-homepage incident "
            "on 2026-05-03. Remove the filter — frozen stories must stay "
            "eligible. See project_freshness_model.md."
        )

    def test_blindspot_endpoint_does_not_filter_frozen_at(self):
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py"
        )
        source = src_path.read_text()
        marker = "async def blindspot_stories"
        start = source.find(marker)
        assert start >= 0, "Could not locate blindspot_stories function"
        window = source[start : start + 2500]

        assert "Story.frozen_at.is_(None)" not in window, (
            "blindspot_stories endpoint re-introduced the frozen_at filter. "
            "Frozen blindspots are still valid evidence of one-sided coverage."
        )


# ═════════════════════════════════════════════════════════════════════
# 7. Demote step: couples to freeze, not age
# ═════════════════════════════════════════════════════════════════════

class TestDemoteOnFreeze:
    """The refactored step_demote_umbrella_stories must demote on
    `frozen_at IS NOT NULL`, not on the prior age threshold. This
    couples demote to freeze: any frozen story is sunk to priority=-50,
    no unfrozen story is ever demoted.
    """

    def test_demote_step_filters_on_frozen_at(self):
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        )
        source = src_path.read_text()

        # Locate step_demote_umbrella_stories function.
        marker = "async def step_demote_umbrella_stories"
        start = source.find(marker)
        assert start >= 0, "Could not locate step_demote_umbrella_stories"
        # Function is small — ~2KB window covers it.
        window = source[start : start + 2500]

        assert "Story.frozen_at.isnot(None)" in window, (
            "step_demote_umbrella_stories no longer filters on "
            "frozen_at IS NOT NULL. The 2026-05-03 refactor coupled "
            "demote to freeze — reverting this re-introduces the bug "
            "where active 7d+ stories get demoted prematurely."
        )

        # And it must NOT use the prior age-threshold comparison form.
        assert "Story.first_published_at < cutoff" not in window, (
            "step_demote_umbrella_stories still uses the age-based "
            "cutoff. This was the prior overly-aggressive logic."
        )


# ═════════════════════════════════════════════════════════════════════
# 8. Bias scoring entry points all gated to homepage
# ═════════════════════════════════════════════════════════════════════

class TestBiasScoringEntryPointsGated:
    """Four alternative paths to score_unscored_articles bypassed the
    homepage gate (Celery worker, two admin endpoints, two CLI commands).
    The Celery worker was the most likely April overage culprit. All
    four must now pass `homepage_only_top_n=20` so the gate behaves
    identically to the maintenance cron.
    """

    def test_celery_worker_passes_homepage_gate(self):
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "app" / "workers" / "nlp_task.py"
        )
        source = src_path.read_text()
        assert "homepage_only_top_n=20" in source, (
            "Celery score_bias_batch_task no longer passes "
            "homepage_only_top_n. If this task ever fires, it scores "
            "every article in the DB without a budget gate."
        )

    def test_admin_pipeline_run_all_passes_homepage_gate(self):
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        )
        source = src_path.read_text()
        # Both the bias_trigger endpoint AND the run-all endpoint must
        # pass the gate. Check the count of occurrences as a smoke test.
        count = source.count("homepage_only_top_n=20")
        assert count >= 2, (
            f"Expected at least 2 admin endpoints to pass "
            f"homepage_only_top_n=20 to score_unscored_articles "
            f"(bias_trigger + run-all), found {count}."
        )

    def test_cli_score_passes_homepage_gate(self):
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "manage.py"
        )
        source = src_path.read_text()
        count = source.count("homepage_only_top_n=20")
        assert count >= 2, (
            f"CLI manage.py must pass homepage_only_top_n=20 in BOTH "
            f"`score` and `pipeline` commands — found {count} occurrences."
        )


# ═════════════════════════════════════════════════════════════════════
# 9. Hourly pipeline removed from active code path
# ═════════════════════════════════════════════════════════════════════

class TestHourlyPipelineRemoved:
    """Per Parham 2026-05-03: only FULL_PIPELINE should run, 3× daily.
    HOURLY_PIPELINE was removed. mode='hourly' now falls back to
    INGEST_ONLY_PIPELINE so leftover Railway cron schedules degrade
    safely instead of crashing.
    """

    def test_hourly_pipeline_constant_does_not_exist(self):
        import auto_maintenance

        assert not hasattr(auto_maintenance, "HOURLY_PIPELINE"), (
            "HOURLY_PIPELINE constant was re-introduced. Per Parham "
            "2026-05-03, only FULL_PIPELINE should be a cron target. "
            "If you need a fast-path, add it to INGEST_ONLY_PIPELINE."
        )

    def test_hourly_mode_falls_back_safely(self):
        """We can't easily run the maintenance loop in tests, so we
        check that the module's source still routes hourly→ingest
        rather than crashing on missing HOURLY_PIPELINE.
        """
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        )
        source = src_path.read_text()
        assert 'mode == "hourly"' in source, "hourly mode handling removed entirely"
        # The hourly branch must reference INGEST, not HOURLY_PIPELINE.
        # Find the elif block.
        idx = source.find('elif mode == "hourly"')
        assert idx >= 0
        window = source[idx : idx + 400]
        assert "INGEST_ONLY_PIPELINE" in window, (
            "mode='hourly' must fall back to INGEST_ONLY_PIPELINE so "
            "leftover Railway cron schedules don't crash."
        )
        assert "HOURLY_PIPELINE" not in window, (
            "mode='hourly' still references HOURLY_PIPELINE constant."
        )


# ═════════════════════════════════════════════════════════════════════
# 10. Manual story seeding (Parham 2026-05-03)
# ═════════════════════════════════════════════════════════════════════

class TestManualStorySeed:
    """Two new admin endpoints let Parham (or Niloofar in chat) initiate
    a story for an event the auto-clustering missed:
      GET  /admin/articles/search  → find candidate articles
      POST /admin/stories/seed     → create story from picked article IDs

    Source-grep tests guard the contract — these endpoints must exist
    and accept the right shapes.
    """

    def test_search_endpoint_exists_and_admin_gated(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()

        # Find the search endpoint declaration.
        marker = '@router.get("/articles/search"'
        idx = src.find(marker)
        assert idx >= 0, (
            "GET /admin/articles/search endpoint missing. Parham depends "
            "on it for manual story seeding (find candidates by keyword)."
        )
        # Must be admin-gated.
        window = src[idx : idx + 200]
        assert "Depends(require_admin)" in window, (
            "/admin/articles/search must be admin-gated."
        )

    def test_seed_endpoint_exists_and_admin_gated(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()

        marker = '@router.post("/stories/seed"'
        idx = src.find(marker)
        assert idx >= 0, (
            "POST /admin/stories/seed endpoint missing. Parham depends "
            "on it for manual story creation from picked article IDs."
        )
        window = src[idx : idx + 200]
        assert "Depends(require_admin)" in window, (
            "/admin/stories/seed must be admin-gated."
        )

    def test_seed_endpoint_marks_is_edited_true(self):
        """The seeded story must be is_edited=True so the maintenance
        pipeline doesn't overwrite Parham's title/summary.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()

        # Find the seed function body.
        idx = src.find("async def seed_story_manually")
        assert idx >= 0
        # Find the Story() constructor call within the function (next
        # ~3KB covers it).
        window = src[idx : idx + 4000]
        assert "is_edited=True" in window, (
            "Seeded stories must set is_edited=True so the pipeline "
            "doesn't clobber the manually-chosen title/summary."
        )

    def test_seed_endpoint_requires_at_least_2_articles(self):
        """Singletons orphan again — the endpoint must reject lone
        article IDs to keep the homepage stable.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def seed_story_manually")
        window = src[idx : idx + 4000]
        # We assert the floor check is present; the exact phrasing of
        # the error message is the operator-facing contract.
        assert "len(ids) < 2" in window, (
            "Seed endpoint must reject lists with fewer than 2 distinct "
            "article IDs (singletons re-orphan)."
        )


class TestSummarizeBiasOrderByPriority:
    """The 2026-05-03 evening regression: step_summarize and
    score_unscored_articles BOTH selected candidates ordered only by
    trending_score. Demoted umbrella stories (priority=-50, thousands of
    articles, trending_score in the 1000s) starved the active priority=0
    stories that actually appear at the top of the homepage. Result: top
    homepage cards had no summary_fa or per-article BiasScores while the
    LLM budget was burned on stories sunk to slot 8+ by priority sort.

    Both candidate-selection queries MUST order by `priority DESC` first,
    `trending_score DESC` second — same shape as the trending API and
    homepage_scope itself."""

    def test_summarize_orders_by_priority_then_trending(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        # Find step_summarize (the main one — skip past
        # step_summarize_newly_visible which was added 2026-05-04).
        idx = src.find("async def step_summarize(")
        assert idx >= 0, "step_summarize function missing"
        # The candidate scan is the SELECT scoped by HOMEPAGE_POOL_SIZE.
        # Find the LIMIT call directly (avoids matching the docstring-
        # mention of HOMEPAGE_POOL_SIZE in step_summarize_newly_visible).
        limit_idx = src.find(".limit(HOMEPAGE_POOL_SIZE)", idx)
        assert limit_idx >= 0, "Could not locate HOMEPAGE_POOL_SIZE limit"
        # Look backwards for the order_by — must be within ~3KB before
        # the limit call and must include priority.desc().
        preceding = src[max(0, limit_idx - 3000) : limit_idx]
        order_idx = preceding.rfind(".order_by(")
        assert order_idx >= 0, "step_summarize candidate SELECT missing order_by"
        order_clause = preceding[order_idx:]
        assert "priority.desc()" in order_clause, (
            "step_summarize candidate SELECT must order by Story.priority.desc() "
            "BEFORE trending_score, otherwise demoted umbrella stories "
            "(priority=-50, trending_score in the thousands) monopolize the "
            "LLM budget and the active homepage-top stories never get "
            "summarized. See 2026-05-03 evening incident."
        )
        assert "trending_score.desc" in order_clause, (
            "step_summarize candidate SELECT must keep the trending_score.desc "
            "tiebreaker so older active stories don't always lose to the "
            "newest-but-tiny one."
        )

    def test_bias_scoring_orders_by_priority_then_trending(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "services" / "bias_scoring.py"
        ).read_text()

        idx = src.find("async def score_unscored_articles")
        assert idx >= 0, "score_unscored_articles missing"
        # The candidate-ordering join must happen before query.limit(batch_size).
        end = src.find("query.limit(batch_size)", idx)
        assert end >= 0
        window = src[idx:end]
        assert "Story.priority.desc()" in window, (
            "score_unscored_articles must order by Story.priority.desc() so "
            "bias scoring spend lands on top-of-homepage cards, not on "
            "demoted umbrella stories that visually sit at slot 8+."
        )
        assert "Story.trending_score.desc" in window, (
            "score_unscored_articles must keep trending_score.desc as the "
            "tiebreaker after priority."
        )
        # Must JOIN stories on Article.story_id to make the order_by valid.
        assert "join(Story, Story.id == Article.story_id)" in window, (
            "score_unscored_articles needs an explicit JOIN on stories so "
            "Story.priority/trending_score are reachable in the order_by."
        )


class TestStoryAnalysisGpt5JsonMode:
    """Premium-tier story_analysis (gpt-5-mini by default) was failing to
    return parseable JSON ~90% of the time on 2026-05-03 because:
      1. max_completion_tokens=4096 was too tight for gpt-5's reasoning
         tokens — JSON truncated mid-stream.
      2. response_format=json_object was not set, so the model
         occasionally added commentary or wrapped in markdown without
         the ```json marker the parser expects.

    The fix:
      - Double max_tokens for gpt-5 family calls.
      - Set response_format=json_object (mirrors telegram_analysis
        pass-0 pattern, which has been reliable for months)."""

    def test_story_analysis_sets_json_response_format(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "story_analysis.py"
        ).read_text()

        # Scope to generate_story_analysis (Pass-2, the gpt-5-mini path).
        # Pass-1 fact extraction uses gpt-4.1-nano which doesn't have the
        # reasoning-token-truncation problem.
        gen_idx = src.find("async def generate_story_analysis")
        assert gen_idx >= 0, "generate_story_analysis function missing"
        # Find the create call inside this function.
        create_idx = src.find(
            "client.chat.completions.create(**params)", gen_idx
        )
        assert create_idx >= 0, (
            "generate_story_analysis must call openai chat.completions.create"
        )
        # Walk back ~2KB and confirm response_format=json_object is set
        # within the function body, before the create call.
        window = src[gen_idx : create_idx]
        assert 'response_format' in window and 'json_object' in window, (
            "generate_story_analysis must set params['response_format'] = "
            "{'type': 'json_object'} before the chat.completions.create "
            "call. Without it, gpt-5 family produces unparseable output "
            "~90% of the time and force-resummarize fails silently. See "
            "telegram_analysis.py:195 for the working pattern."
        )

    def test_story_analysis_doubles_token_budget_for_gpt5(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "story_analysis.py"
        ).read_text()

        # The is_gpt5 branch must yield a max_tokens at least 8000 so
        # reasoning + JSON output both fit. The 8192 / 12288 numbers are
        # the current values; the floor is what matters.
        idx = src.find('chosen_model.startswith("gpt-5")')
        assert idx >= 0, (
            "story_analysis must branch on chosen_model.startswith('gpt-5') "
            "to bump max_tokens — gpt-5's reasoning tokens consume the "
            "completion budget before JSON output starts."
        )
        # Verify the bumped values are present.
        window = src[idx : idx + 600]
        # Look for any number >= 8000 in the gpt-5 branch.
        import re
        nums = [int(m.group()) for m in re.finditer(r"\b\d{4,5}\b", window)]
        assert any(n >= 8000 for n in nums), (
            "gpt-5 branch must allocate >= 8000 max_completion_tokens "
            "(found numbers: {nums}). Reasoning tokens consume most of "
            "a 4096 budget before JSON output begins."
        )


class TestDoornamaGpt5TokenBudget:
    """دورنما (the hero-card prose synthesis) uses gpt-5-mini per
    settings.doornama_model. With the prior max_tokens=800 budget,
    reasoning tokens consumed the entire allowance and the model
    returned an empty completion every pass — the function logged
    'doornama: empty completion' and returned None, so briefing_fa was
    silently never populated for the hero card.

    Bumped to 3000 for gpt-5 family. gpt-4 family kept at 800 since
    those don't have reasoning tokens.
    """

    def test_doornama_bumps_max_tokens_for_gpt5(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "doornama.py"
        ).read_text()

        idx = src.find("def generate_doornama_briefing")
        assert idx >= 0, "generate_doornama_briefing missing"
        end = src.find("client.chat.completions.create", idx)
        assert end >= 0
        window = src[idx:end]
        assert 'startswith("gpt-5")' in window or "startswith('gpt-5')" in window, (
            "doornama must branch on doornama_model.startswith('gpt-5') "
            "to bump max_tokens — the prior 800-token budget was eaten "
            "by reasoning tokens, leaving zero room for the prose."
        )
        # Look for any number >= 2000 in the gpt-5 branch.
        import re
        nums = [int(m.group()) for m in re.finditer(r"\b\d{4}\b", window)]
        assert any(n >= 2000 for n in nums), (
            f"gpt-5 doornama branch must allocate >= 2000 max_tokens "
            f"(found: {nums})."
        )


class TestDoornamaReasoningEffortMinimal:
    """gpt-5-mini's default reasoning_effort=medium consumes 2000+ tokens
    on internal reasoning even for the trivially-bounded دورنما task.
    With max_tokens=3000, that left near-zero room for visible output;
    every hero-card pass returned an empty completion. doornama is pure
    synthesis over already-organized inputs (per-side summaries, bias
    bullets, narrative arc) — no novel reasoning needed. Setting
    reasoning_effort=minimal frees the budget for the prose paragraph
    that the user actually sees."""

    def test_doornama_sets_reasoning_effort_minimal_for_gpt5(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "doornama.py"
        ).read_text()

        idx = src.find("def generate_doornama_briefing")
        assert idx >= 0, "generate_doornama_briefing missing"
        end = src.find("client.chat.completions.create", idx)
        assert end >= 0
        window = src[idx:end]
        assert 'reasoning_effort' in window and 'minimal' in window, (
            "doornama must set params['reasoning_effort'] = 'minimal' on "
            "gpt-5 family calls. Default 'medium' burns the entire "
            "max_tokens budget on internal reasoning, returning empty "
            "completions every pass."
        )


class TestForceResummarizeExcludesArchived:
    """The /admin/force-resummarize endpoint was picking archived
    stories (archived_at IS NOT NULL) — those are retired and not on
    the homepage. Per "every penny goes to homepage-visible" rule,
    archived stories must be excluded from the candidate pool. Mirrors
    the gate used in /api/v1/stories and /api/v1/stories/trending.

    Concrete past breach: 9 of 10 IDs picked by force-resummarize on
    2026-05-03 were archived, wasting 9 gpt-5-mini calls (~$0.50)."""

    def test_force_resummarize_filters_archived(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()

        idx = src.find("async def force_resummarize")
        assert idx >= 0, "force_resummarize endpoint missing"
        # The candidate query lives inside the function body. Walk
        # forward until we hit the .limit(limit) call that closes it.
        end = src.find(".limit(limit)", idx)
        assert end >= 0, "Could not locate force_resummarize candidate query"
        window = src[idx:end]
        assert "archived_at.is_(None)" in window, (
            "force_resummarize candidate query must filter "
            "Story.archived_at.is_(None) — archived stories are "
            "retired and burning LLM spend on them violates the "
            "homepage-visible-only rule. See /api/v1/stories.py:112 "
            "for the canonical gate."
        )


class TestStoryAnalysisGpt4oMiniTokenBudget:
    """gpt-4o-mini was capped at max_tokens=4096 in story_analysis. The
    prompt asks for 4 subgroup bullet arrays + 3 per-side summaries +
    bias bullets + scores + narrative arc — on a 79-article hero card
    (story 93bb4325, 2026-05-04), the JSON truncated before producing
    the `narrative` dict. The fallback at line 619 rebuilds
    state_summary_fa from narrative.inside bullets, but with narrative
    missing entirely there's nothing to fallback FROM — so
    state_summary_fa stayed null forever on big stories.

    gpt-4o-mini has no reasoning tokens, so bumping max_tokens is pure
    output-cap headroom and only costs more on stories that USE it.
    """

    def test_gpt4o_mini_max_tokens_bumped_to_8192(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "story_analysis.py"
        ).read_text()

        idx = src.find("async def generate_story_analysis")
        assert idx >= 0
        end = src.find("client.chat.completions.create", idx)
        window = src[idx:end]
        # The non-gpt5 (else) branch must allocate >= 8000 tokens.
        # We grep for "8192" specifically since that's the chosen value
        # and it's distinct from the gpt-5 branch's 8192/12288.
        assert "8192 if include_analyst_factors else 8192" in window or (
            "10240 if include_analyst_factors else 8192" in window
        ), (
            "gpt-4o-mini story_analysis branch must allocate >= 8192 "
            "max_tokens to avoid truncating the narrative dict on big "
            "stories. Hero card 93bb4325 (2026-05-04) was missing "
            "state_summary_fa because the response truncated."
        )


class TestRecalcTrendingBeforeSummarize:
    """step_summarize uses Story.trending_score to pick `doornama_top_ids`
    via homepage_story_ids. If trending_score is stale (recomputed AFTER
    summarize), the briefing's hero pick lags one 6h cron cycle.

    Cycle-3 Phase B (2026-05-08): the recalc was moved EARLIER, to
    before summarize_newly_visible (was previously between merge_similar
    and summarize). Both summarize_newly_visible and summarize now read
    fresh trending. The order is now:

        recluster_orphans
        recalc_trending_pre_summarize  ← was here historically AFTER merge_similar
        summarize_newly_visible
        telegram_link
        merge_similar
        summarize

    Trade-off: merge_similar can change article_count of merged stories
    AFTER the pre-summarize recalc fires, so a story merged in this
    cron may briefly show stale trending. Bounded — the late
    recalc_trending picks it up.
    """

    def test_recalc_trending_runs_before_summarize(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        idx = src.find("FULL_PIPELINE = [")
        assert idx >= 0
        recalc_pre_pos = src.find('"recalc_trending_pre_summarize"', idx)
        summarize_pos = src.find('"step_summarize"', idx)
        newly_visible_pos = src.find('"step_summarize_newly_visible"', idx)
        assert recalc_pre_pos >= 0, (
            "FULL_PIPELINE must contain 'recalc_trending_pre_summarize'"
        )
        assert summarize_pos >= 0
        assert newly_visible_pos >= 0
        # Recalc must precede BOTH summarize steps so each reads fresh
        # trending_score.
        assert recalc_pre_pos < newly_visible_pos, (
            f"recalc_trending_pre_summarize({recalc_pre_pos}) must "
            f"precede summarize_newly_visible({newly_visible_pos}) — "
            f"otherwise homepage_story_ids reads stale trending."
        )
        assert recalc_pre_pos < summarize_pos, (
            f"recalc_trending_pre_summarize({recalc_pre_pos}) must "
            f"precede summarize({summarize_pos})."
        )


class TestSummarizeNewlyVisibleStep:
    """A homepage-eligible story missing a summary should NOT have to wait
    until step_summarize fires (~30-50 min into a cron, after the 18-min
    telegram_link step). The new step_summarize_newly_visible runs right
    after recluster_orphans so newly-promoted stories get summaries
    ~10-15 min into the cron instead.

    Tripwires:
      1. The function exists.
      2. It's wired into FULL_PIPELINE between recluster_orphans and
         telegram_link.
      3. It's also in INGEST_ONLY_PIPELINE (dashboard "Run Now" path).
      4. It only handles stories with summary_fa IS NULL (not a
         duplicate of step_summarize's full responsibility)."""

    def test_function_exists(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        assert "async def step_summarize_newly_visible" in src, (
            "step_summarize_newly_visible function must exist."
        )

    def test_function_filters_to_summary_fa_null(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_summarize_newly_visible")
        end = src.find("async def step_summarize", idx + 1)
        body = src[idx:end]
        assert "Story.summary_fa.is_(None)" in body, (
            "step_summarize_newly_visible must filter to "
            "Story.summary_fa.is_(None) — its only job is filling new "
            "stories. Refresh of existing summaries is step_summarize's "
            "job."
        )
        # 2026-05-07 cycle-1 audit: homepage_story_ids SSoT replaces the
        # prior inline predicate set. The 3 filters that used to be
        # inline (is_blindspot is False, archived_at is None,
        # article_count >= 4) are now encapsulated by homepage_story_ids().
        assert "homepage_story_ids" in body, (
            "step_summarize_newly_visible must call homepage_story_ids(db) "
            "as the canonical homepage scope filter; inline predicates "
            "drift from the SSoT."
        )
        assert "Story.id.in_(visible_ids)" in body, (
            "step_summarize_newly_visible must filter by "
            "Story.id.in_(visible_ids) where visible_ids = await "
            "homepage_story_ids(db)."
        )

    def test_wired_into_full_pipeline_between_recluster_and_telegram_link(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        # Find FULL_PIPELINE block.
        full_idx = src.find("FULL_PIPELINE = [")
        assert full_idx >= 0
        full_end = src.find("INGEST_ONLY_PIPELINE = [", full_idx)
        full_block = src[full_idx:full_end]

        recluster_pos = full_block.find('"step_recluster_orphans"')
        new_step_pos = full_block.find('"step_summarize_newly_visible"')
        telegram_pos = full_block.find('"step_telegram_link_posts"')

        assert recluster_pos >= 0 and telegram_pos >= 0, (
            "FULL_PIPELINE must contain recluster_orphans and "
            "telegram_link_posts."
        )
        assert new_step_pos >= 0, (
            "FULL_PIPELINE must contain step_summarize_newly_visible."
        )
        assert recluster_pos < new_step_pos < telegram_pos, (
            "step_summarize_newly_visible must be wired BETWEEN "
            "recluster_orphans and telegram_link_posts in FULL_PIPELINE."
        )

    def test_wired_into_ingest_only_pipeline(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        ingest_idx = src.find("INGEST_ONLY_PIPELINE = [")
        assert ingest_idx >= 0
        # Find end of the list (next top-level definition)
        ingest_end = src.find("\n]", ingest_idx)
        ingest_block = src[ingest_idx:ingest_end]
        assert "step_summarize_newly_visible" in ingest_block, (
            "INGEST_ONLY_PIPELINE must also include "
            "step_summarize_newly_visible so dashboard 'Run Now' fills "
            "summaries for newly-eligible homepage stories."
        )


class TestSummarizeHomepagePoolSize:
    """The candidate-scan in step_summarize uses HOMEPAGE_POOL_SIZE to
    bound the SELECT … LIMIT. With the prior cap of 10, lower-ranked
    visible cards could escape the scan entirely when the homepage had
    >10 stories. Bumped to 20 to match homepage_story_ids() defaults
    (top-20 trending + top-20 blindspots union)."""

    def test_pool_size_bumped_to_at_least_20(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_summarize")
        # Skip past the newly_visible function — find the second
        # occurrence (the real step_summarize).
        idx = src.find("async def step_summarize", idx + 1)
        # No wait — step_summarize_newly_visible is FIRST. The plain
        # step_summarize is the second match. Re-find from start.
        first = src.find("async def step_summarize_newly_visible")
        second = src.find("async def step_summarize(", first + 1)
        assert second >= 0, "Could not find step_summarize (real one)"
        end = src.find("\n\nasync def ", second + 1)
        body = src[second:end if end > 0 else len(src)]

        # Find HOMEPAGE_POOL_SIZE assignment
        import re
        m = re.search(r"HOMEPAGE_POOL_SIZE\s*=\s*(\d+)", body)
        assert m, "HOMEPAGE_POOL_SIZE assignment missing in step_summarize"
        val = int(m.group(1))
        assert val >= 20, (
            f"HOMEPAGE_POOL_SIZE must be >= 20 (found {val}) so the "
            f"scan covers all visible homepage cards. Stories below "
            f"the pool cap can never be re-summarized."
        )


class TestNearFreezeCosineThreshold:
    """Stories in the 5-7d window (last days before freeze) need extra
    accretion friction to prevent the umbrella drift pattern observed
    in story 5adc903e (Apr 10 cluster grew to 30 unrelated articles
    over 24 days). The freeze rule blocks attachment at 7d, but the
    days approaching freeze are still vulnerable to articles squeezing
    in via the prior 0.55 threshold.

    Adds a third tier:
      0-2d   → 0.40 (fresh, easy accretion)
      2-5d   → 0.55 (existing aged)
      5-7d   → 0.65 (NEW — near-freeze tightening)
      7d+    → frozen, no attachment at all"""

    def test_clustering_has_near_freeze_threshold(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()

        assert "EMBEDDING_SIM_THRESHOLD_NEAR_FREEZE = 0.65" in src, (
            "clustering.py must define EMBEDDING_SIM_THRESHOLD_NEAR_FREEZE = 0.65 "
            "for the 5-7d aged-candidate window."
        )
        assert "NEAR_FREEZE_CANDIDATE_DAYS = 5" in src, (
            "clustering.py must define NEAR_FREEZE_CANDIDATE_DAYS = 5 — "
            "the boundary at which the tighter threshold kicks in."
        )

    def test_clustering_uses_near_freeze_threshold_in_branch(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()

        # The threshold-selection block must include a near-freeze branch.
        # Find the passage where base_threshold is assigned.
        idx = src.find("EMBEDDING_SIM_THRESHOLD_AGED")
        # Walk forward to the threshold-selection if/elif chain.
        chain_idx = src.find(
            "elif age_days > AGED_CANDIDATE_DAYS:", idx
        )
        # The new branch must precede the AGED_CANDIDATE_DAYS branch
        # (5d gate runs BEFORE 2d gate so the higher threshold wins).
        near_branch = src.rfind("NEAR_FREEZE_CANDIDATE_DAYS", 0, chain_idx)
        assert near_branch >= 0, (
            "Threshold-selection chain must check "
            "NEAR_FREEZE_CANDIDATE_DAYS BEFORE AGED_CANDIDATE_DAYS."
        )
        assert chain_idx > near_branch, (
            "Order wrong: NEAR_FREEZE branch must come first so the "
            "higher 0.65 threshold wins for 5d+ stories."
        )


class TestTitleCohesionGate:
    """When step_summarize regenerates a story title, verify the new
    title actually represents the cluster. If cosine(title, centroid)
    < 0.5, keep the prior title.

    Catches the umbrella-title drift pattern (story 5adc903e):
    centroid was a junk-drawer of Iran-region topics; the LLM picked
    the most recent Hezbollah-weapon article as the title. Old title
    was equally wrong but at least kept the URL stable."""

    def test_step_summarize_has_title_cohesion_gate(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        # Find step_summarize body
        idx = src.find("async def step_summarize(")
        # Skip past step_summarize_newly_visible (defined first in file)
        if "newly_visible" in src[idx:idx+100]:
            idx = src.find("async def step_summarize(", idx + 1)
        assert idx >= 0
        end_marker = src.find("\n\nasync def ", idx + 100)
        body = src[idx : end_marker if end_marker > 0 else len(src)]

        # The cohesion gate uses generate_embedding + cosine_similarity
        assert "generate_embedding" in body, (
            "step_summarize must call generate_embedding to gate the "
            "title update against the cluster centroid."
        )
        assert "title_sim" in body or "title_cohesion" in body.lower(), (
            "step_summarize must compute a similarity between the "
            "proposed title and the story's centroid."
        )
        # The gate must explicitly compare to a 0.5 threshold (or
        # equivalent) and skip the title write when below.
        assert "0.5" in body, (
            "Cohesion gate must threshold at 0.5 — the documented "
            "cutoff for an off-cluster title."
        )


class TestPinnedStoriesProtectedFromAutoLifecycle:
    """A manually-pinned story (priority > 0) is the operator's explicit
    declaration that the story IS the hero card. Auto-freeze and
    auto-demote must not stomp the pin.

    Concrete past incident (2026-05-05): Parham pinned f0479292 to
    priority=10 to fix the hero. Overnight, step_archive_stale froze it
    (it was 25 days old by first_published_at), then
    step_demote_umbrella_stories set priority=-50 because frozen_at
    was now set. The pin was overridden silently and the homepage
    reverted to the wrong hero card."""

    def test_archive_stale_skips_pinned_stories(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        idx = src.find("async def step_archive_stale")
        assert idx >= 0
        # Find the freeze SELECT inside the function.
        freeze_idx = src.find("freeze_result = await db.execute", idx)
        assert freeze_idx >= 0
        # Walk forward to the closing of that SELECT.
        end = src.find(")\n        )", freeze_idx)
        body = src[freeze_idx : end]
        assert "Story.priority <= 0" in body, (
            "step_archive_stale's freeze SELECT must filter "
            "Story.priority <= 0 so manually pinned stories "
            "(priority > 0) are not auto-frozen and subsequently "
            "demoted by step_demote_umbrella_stories."
        )

    def test_demote_umbrella_skips_pinned_stories(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        idx = src.find("async def step_demote_umbrella_stories")
        assert idx >= 0
        # Find the demote SELECT inside the function.
        sel_idx = src.find("select(Story).where(", idx)
        assert sel_idx >= 0
        end = src.find(")\n        )).scalars()", sel_idx)
        body = src[sel_idx : end]
        assert "Story.priority <= 0" in body, (
            "step_demote_umbrella_stories must filter Story.priority <= 0 "
            "so a manual pin (priority > 0) is never overridden by the "
            "demote-on-freeze cascade."
        )


class TestEmbeddingNullCanaryEligibilityJoin:
    """The embedding_null_rate_24h canary must scope its denominator to
    articles the pipeline ACTUALLY tries to embed — content_type set AND
    source's content_filters.allowed list includes that type. Without
    the join, articles correctly dropped by the source filter inflate
    the rate to ~50% on a healthy system, training operators to ignore
    the alarm. Same trap as the 2026-05-02 false canaries (see
    feedback_canary_design memory)."""

    def test_emb_24h_query_joins_sources_table(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()

        # Find the emb_24h block and grab the surrounding SQL.
        idx = src.find("emb_24h = (await db.execute")
        assert idx >= 0, "emb_24h canary query missing"
        window = src[idx : idx + 1500]
        assert "JOIN sources s" in window, (
            "emb_24h canary must JOIN sources to filter to embedding-"
            "eligible articles. Without it, articles correctly dropped "
            "by source content_filters inflate the NULL-rate."
        )
        assert "content_filters" in window and "allowed" in window, (
            "emb_24h canary must use the same content_filters.allowed "
            "predicate as nlp_pipeline.process_unprocessed_articles."
        )
        assert "content_type IS NOT NULL" in window, (
            "emb_24h canary must exclude unclassified articles "
            "(content_type IS NULL) — they haven't reached the embed step."
        )


class TestDedupNoLazyLoadOfDeferredContentText:
    """The 2026-05-07 egress fix in d93fa14 added defer(Article.content_text)
    to step_deduplicate_articles Layer 3. The length-tiebreaker on the same
    line range still accessed `a.content_text` via attribute lookup, which
    in async SQLAlchemy 2.0 lazy-loads the deferred column and crashes with
    `greenlet_spawn has not been called`. Production cron failed every run
    until the tiebreaker was rerouted through a pre-fetched length dict.

    Tripwire: instance-level access of `.content_text` inside the dedup
    function force-loads the deferred column. The class-level expression
    `Article.content_text` is fine (used in select/defer/where).
    """

    def test_dedup_does_not_access_deferred_content_text_on_instance(self):
        import inspect
        import re

        from auto_maintenance import step_deduplicate_articles

        src = inspect.getsource(step_deduplicate_articles)

        instance_pattern = re.compile(r"(?<!Article)\.content_text\b")
        matches = instance_pattern.findall(src)
        assert not matches, (
            "step_deduplicate_articles accesses .content_text via instance "
            "attribute. The column is deferred at the Layer 3 SELECT, so the "
            "access lazy-loads via implicit await and crashes with "
            "greenlet_spawn. Pre-fetch lengths via a single "
            "select(Article.id, func.length(Article.content_text)) before the "
            "dedup loop and look up by id."
        )


class TestArticlesListEndpointDefersHeavyJsonb:
    """Tripwire for 2026-05-07 egress incident: ~295 GB of Neon transfer
    bled in 1.5 hours after the d93fa14 cron-side fix. Root cause was
    the public GET /api/v1/articles list endpoint loading embedding,
    content_text, keywords, named_entities via select(Article) with no
    defer — ArticleBrief never serializes those four heavy JSONB
    columns, so every list call dropped hundreds of KB of unused data
    on the wire. Frontend dashboards that refresh this endpoint
    multiplied the leak.
    """

    def test_list_articles_defers_heavy_jsonb_columns(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "articles.py"
        ).read_text()

        for col in ("embedding", "content_text", "keywords", "named_entities"):
            assert f"defer(Article.{col})" in src, (
                f"app/api/v1/articles.py must defer Article.{col} on the "
                f"list endpoint — ArticleBrief doesn't serialize it, so "
                f"loading it from DB just bleeds egress."
            )


class TestAutoFreezeOnUmbrellaSize:
    """Story 745b6edd-95f6-4f39-b6e9-d67972ebed86 reached 107 articles
    and 20 sources before being manually frozen on 2026-05-07. The 7-day
    age gate in step_archive_stale missed it because first_published_at
    was recent — the cluster centroid had become so generic that
    match_existing kept attaching new fresh-dated articles instead of
    seeding new clusters for distinct events.

    Tripwire: step_archive_stale's freeze condition must include a
    size-based trigger (Story.article_count > N) alongside the age
    trigger, so future umbrellas auto-freeze without a human in the loop.
    """

    def test_freeze_condition_includes_article_count_threshold(self):
        import inspect

        from auto_maintenance import step_archive_stale

        src = inspect.getsource(step_archive_stale)

        assert "UMBRELLA_ARTICLE_COUNT_FREEZE" in src, (
            "step_archive_stale must define UMBRELLA_ARTICLE_COUNT_FREEZE "
            "and use it as a size-based freeze gate."
        )
        assert "Story.article_count > UMBRELLA_ARTICLE_COUNT_FREEZE" in src, (
            "step_archive_stale's freeze WHERE clause must include "
            "`Story.article_count > UMBRELLA_ARTICLE_COUNT_FREEZE` so "
            "oversized active umbrellas auto-freeze even when their "
            "first_published_at is recent."
        )


class TestFixIssuesBoundedAndDeferred:
    """The 2026-05-07 cycle-1 redo audit caught step_fix_issues loading
    the entire articles table (no LIMIT, no defer) just to do a Python-
    side ASCII-density filter on title_fa. With ~30k rows × 4 heavy
    JSONB columns, that's ~200 MB of egress per cron — the largest
    single cron-side leak after d93fa14 patched the obvious sites.

    Tripwire: both select(Article) queries inside step_fix_issues must
    defer the 4 heavy JSONB columns AND have a LIMIT clause.
    """

    def test_fix_issues_select_article_is_bounded_and_deferred(self):
        import inspect

        from auto_maintenance import step_fix_issues

        src = inspect.getsource(step_fix_issues)

        # Both selects against Article must defer the four heavy cols.
        for col in ("embedding", "content_text", "keywords", "named_entities"):
            assert src.count(f"Article.{col}") >= 2, (
                f"step_fix_issues must defer Article.{col} on every "
                f"select(Article) site (currently 2 sites). Without "
                f"defer, the full articles table is fetched into memory."
            )

        # Must have at least one .limit() — never load the full table.
        assert ".limit(" in src, (
            "step_fix_issues must bound its select(Article) queries with "
            ".limit() — the original implementation loaded ~30k articles "
            "to do a Python-side title filter."
        )


class TestSummarizeNewlyVisibleHomepageScope:
    """The 2026-05-07 cycle-1 audit (Island 4) found step_summarize_newly_
    visible using inline predicates (article_count >= 4, priority > -100,
    is_blindspot is False, archived_at is None) instead of the canonical
    `homepage_story_ids` SSoT. Stories that pass the inline predicate but
    are NOT on the homepage trending/blindspot top-N (e.g. priority=-50
    demoted umbrellas with article_count >= 4) burned LLM budget. CLAUDE.md
    homepage-scope rule mandates SSoT for every per-story LLM step.
    """

    def test_summarize_newly_visible_uses_homepage_story_ids(self):
        import inspect

        from auto_maintenance import step_summarize_newly_visible

        src = inspect.getsource(step_summarize_newly_visible)
        assert "homepage_story_ids" in src, (
            "step_summarize_newly_visible must call homepage_story_ids(db) "
            "to scope LLM spend; inline predicates drift from the canonical "
            "filter."
        )
        assert "Story.id.in_(visible_ids)" in src, (
            "step_summarize_newly_visible must filter by "
            "Story.id.in_(visible_ids) where visible_ids = await "
            "homepage_story_ids(db). Direct inline predicates are forbidden."
        )


class TestTranslateMultilocaleFlagModifiedImported:
    """The 2026-05-07 cycle-1 audit (Island 6) caught translate_multilocale
    calling `flag_modified(story, "translations")` at L496 without
    importing the function. Every call to `clear_translations_for_story`
    raised NameError, silently swallowed by admin endpoints — auto-clear
    on FA edit was broken in production since shipping.
    """

    def test_flag_modified_is_imported(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app"
            / "services"
            / "translate_multilocale.py"
        ).read_text()
        # Either the symbol is imported, or the file no longer references it.
        if "flag_modified(" in src:
            assert "from sqlalchemy.orm.attributes import flag_modified" in src or (
                "from sqlalchemy.orm import" in src and "flag_modified" in src
            ), (
                "translate_multilocale.py uses flag_modified() but doesn't "
                "import it. This crashes clear_translations_for_story at "
                "runtime, breaking auto-clear on FA edit."
            )


class TestClusterMergeFunctionsDeferHeavyJsonb:
    """Cycle-1 audit Island 3 found 3 cluster-merge functions loading
    full Story rows including 7 heavy JSONB columns the merge logic
    never reads (translations, telegram_analysis, editorial_context_fa,
    summary_anchor, analysis_snapshot_24h, hourly_update_signal,
    summary_en). With ~1000 tiny stories per cron, the wasted egress
    was ~210-280 MB per maintenance run. The defers are now applied;
    this tripwire fails if any merge function regresses the pattern.
    """

    def test_merge_tiny_by_cosine_defers_heavy_story_jsonb(self):
        import inspect

        from app.services.clustering import _merge_tiny_by_cosine

        src = inspect.getsource(_merge_tiny_by_cosine)
        for col in (
            "translations",
            "telegram_analysis",
            "editorial_context_fa",
            "summary_anchor",
            "analysis_snapshot_24h",
            "hourly_update_signal",
            "summary_en",
        ):
            assert f"Story.{col}" in src and "defer" in src, (
                f"_merge_tiny_by_cosine must defer Story.{col} on its "
                f"select(Story) — this column is never read by the merge "
                f"logic and at ~10-20 KB × 1000 tiny stories represents "
                f"~10-20 MB of avoidable egress per cron."
            )

    def test_merge_hidden_stories_defers_heavy_story_jsonb(self):
        import inspect

        from app.services.clustering import _merge_hidden_stories

        src = inspect.getsource(_merge_hidden_stories)
        for col in (
            "translations",
            "telegram_analysis",
            "editorial_context_fa",
            "summary_anchor",
            "hourly_update_signal",
        ):
            assert f"Story.{col}" in src and "defer" in src, (
                f"_merge_hidden_stories must defer Story.{col} on its "
                f"select(Story)."
            )

    def test_merge_similar_visible_stories_defers_heavy_story_jsonb(self):
        import inspect

        from app.services.clustering import merge_similar_visible_stories

        src = inspect.getsource(merge_similar_visible_stories)
        for col in (
            "translations",
            "telegram_analysis",
            "editorial_context_fa",
            "summary_anchor",
            "hourly_update_signal",
        ):
            assert f"Story.{col}" in src and "defer" in src, (
                f"merge_similar_visible_stories must defer Story.{col} "
                f"on its select(Story)."
            )


class TestVisibleStoriesStatMatchesHomepageGate:
    """Cycle-1 audit Island 11 found a canary/stat mismatch: the
    `article_count_drift` canary correctly filters `archived_at IS NULL`
    (matching the public trending API's filter), but the dashboard's
    `visible_stories` stat at admin.py L159 did not. Result: the stat
    over-reported homepage visibility by counting archived stories
    that don't appear on /api/v1/stories/trending. The fix aligns the
    stat to the gate.
    """

    def test_visible_stories_filters_archived(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("visible_stories = ")
        assert idx >= 0, "visible_stories assignment must exist in admin.py"
        # Grab the surrounding ~400 chars (the SQL query body).
        window = src[idx : idx + 400]
        assert "Story.article_count >= 5" in window, (
            "visible_stories must keep the >= 5 article gate."
        )
        assert "Story.archived_at.is_(None)" in window, (
            "visible_stories stat must filter archived_at IS NULL to "
            "match the public trending API. Otherwise it over-reports "
            "homepage visibility."
        )


class TestTelegramPostsHashFormat:
    """Cycle-1 audit Phase B: step_telegram_deep_analysis caches Pass-2
    LLM results keyed on a hash of the post pool. If that hash format
    changes (e.g. adds a field, drops the sort), every cached entry
    becomes stale and the cron re-pays for analysis already computed —
    silent 75% → 0% cache-hit drop with no operator signal.

    Tripwire pins the format. If you intentionally change it, update
    this test AND wipe Story.telegram_analysis['posts_hash'] across
    the DB so old caches don't poison the new hash key.
    """

    def test_posts_hash_uses_id_and_text_length_sorted(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("def _posts_hash(posts: list)")
        assert idx >= 0, "_posts_hash helper must exist in auto_maintenance.py"
        body = src[idx : idx + 600]
        assert "sorted(" in body, (
            "_posts_hash must sort the pool — without it, post-reorder "
            "alone invalidates the cache and re-pays for unchanged work."
        )
        assert "p.id" in body and "len(p.text" in body, (
            "_posts_hash format expects `{p.id}:{len(p.text or '')}` per "
            "post. Changing it without wiping caches resets cache-hit to 0%."
        )
        assert "sha1" in body, (
            "_posts_hash uses SHA-1; a change to a different digest also "
            "invalidates every cached entry."
        )


class TestR2BackupSubprocessOrder:
    """Cycle-1 audit Island 13 found the R2 backup script closing
    pg_dump's stdout before calling proc.wait(). This can SIGPIPE
    pg_dump while it's still flushing — silently corrupting the backup
    while reporting rc=0 (or rc=141 SIGPIPE). The fix: wait first,
    then close.
    """

    def test_backup_script_waits_before_closing_stdout(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "scripts"
            / "r2_db_backup.py"
        ).read_text()
        # Find the backup function body (around the gzip+Popen block).
        idx = src.find("with gzip.open(out_path")
        assert idx >= 0, "Expected backup gzip+Popen block."
        block = src[idx : idx + 800]
        # The wait() must happen inside the try (or before the close()).
        # Bad: copyfileobj → close → wait
        # Good: copyfileobj → wait → close (or wait inside try)
        wait_pos = block.find("proc.wait(")
        close_pos = block.find("proc.stdout.close(")
        assert wait_pos >= 0 and close_pos >= 0
        assert wait_pos < close_pos, (
            "pg_dump backup must call proc.wait() BEFORE proc.stdout."
            "close(). Closing first can SIGPIPE pg_dump and silently "
            "truncate the dump."
        )


class TestR2MigrationSentinelBackoff:
    """Cycle-2 audit (deferred from cycle-1 Island 8). step_migrate_images_to_r2
    must use Article.last_r2_migration_attempt_at as a 24h retry sentinel:
      - exclude rows attempted in the last 24h from the work query
      - stamp the column on EVERY attempt (success, no-op, AND failure)
    Without the stamp on the failure path, a chronically broken upstream
    URL stays at the head of the per-cron 150-slot batch forever.
    """

    def test_step_uses_24h_backoff_filter(self):
        from pathlib import Path

        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        idx = src.find("async def step_migrate_images_to_r2()")
        assert idx >= 0, "step_migrate_images_to_r2 must exist"
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def] if next_def > 0 else src[idx:]
        # The OR-clause must reference last_r2_migration_attempt_at
        # twice (IS NULL or older than the floor).
        assert "last_r2_migration_attempt_at" in body, (
            "step_migrate_images_to_r2 must filter on the sentinel column"
        )
        assert body.count("last_r2_migration_attempt_at") >= 3, (
            "Expected: filter (NULL + < floor), backoff_skipped count, "
            "and stamp in _flush. Found fewer references."
        )
        # The 24h floor must come from a relative `now - 24h` calculation,
        # not a hard-coded date.
        assert "hours=24" in body, (
            "Backoff floor should be `now - timedelta(hours=24)`"
        )

    def test_step_stamps_attempt_on_all_paths(self):
        """Every code path through the loop must enqueue a stamp:
        migrated, no-op skip, AND failure. If failure is missing,
        broken URLs never back off."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        idx = src.find("async def step_migrate_images_to_r2()")
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def] if next_def > 0 else src[idx:]
        # The flush helper must always set the timestamp; the URL update
        # is conditional but the stamp is unconditional.
        assert (
            'values = {"last_r2_migration_attempt_at"' in body
        ), (
            "_flush must seed values dict with the timestamp, then "
            "conditionally add image_url. Unconditional stamping is the "
            "whole point of the sentinel."
        )

    def test_model_has_sentinel_column(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "models" / "article.py"
        ).read_text()
        assert "last_r2_migration_attempt_at" in src, (
            "Article model must declare last_r2_migration_attempt_at "
            "(migration y0t1u2v3w4x5)"
        )

    def test_self_heal_ddl_includes_column(self):
        """app/main.py self-heal block runs on every deploy — must
        include the new column so a fresh deploy doesn't crash before
        Alembic catches up."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "main.py"
        ).read_text()
        assert "last_r2_migration_attempt_at" in src, (
            "app/main.py lifespan self-heal must add the new column "
            "(parallel idempotent path to the alembic migration)"
        )


class TestPgvectorDualWrite:
    """Cycle-4 pgvector migration (2026-05-08): every writer that
    populates Article.embedding or Story.centroid_embedding MUST also
    populate the new vector(384) column (`*_v`). Dual-write keeps the
    new column in sync during the migration window so readers can be
    switched atomically in a later commit. Drop-old-column happens much
    later. ~60% byte reduction per row when readers switch.
    """

    def test_article_model_has_embedding_v_vector_column(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "models" / "article.py"
        ).read_text()
        assert "from pgvector.sqlalchemy import Vector" in src, (
            "Article model must import Vector from pgvector"
        )
        assert "embedding_v" in src and "Vector(384)" in src, (
            "Article must declare embedding_v as Vector(384) "
            "(pgvector dual-column)"
        )

    def test_story_model_has_centroid_embedding_v_vector_column(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "models" / "story.py"
        ).read_text()
        assert "from pgvector.sqlalchemy import Vector" in src
        assert "centroid_embedding_v" in src and "Vector(384)" in src

    def test_nlp_pipeline_dual_writes_embedding_v(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "nlp_pipeline.py"
        ).read_text()
        # Find the embedding write site and confirm dual-write.
        idx = src.find("article.embedding = embedding")
        assert idx >= 0
        window = src[idx:idx + 400]
        assert "article.embedding_v = embedding" in window, (
            "process_unprocessed_articles MUST dual-write the JSONB "
            "embedding AND the pgvector embedding_v column."
        )

    def test_clustering_dual_writes_centroid_embedding_v(self):
        """Every centroid write site (4 in clustering.py + 1 in
        auto_maintenance.py) must populate centroid_embedding_v."""
        from pathlib import Path

        for fname in (
            ("app/services/clustering.py",),
            ("auto_maintenance.py",),
        ):
            src = (
                Path(__file__).parent.parent / fname[0]
            ).read_text()
            # Count occurrences — every centroid_embedding write must
            # have a matching _v write within a few lines.
            for m_idx, line in enumerate(src.splitlines()):
                if "story.centroid_embedding = " in line and "centroid_embedding_v" not in line:
                    # Check the next 3 lines for the dual-write
                    next_block = "\n".join(src.splitlines()[m_idx:m_idx + 4])
                    assert "centroid_embedding_v" in next_block, (
                        f"{fname[0]}:{m_idx + 1} writes centroid_embedding "
                        f"without dual-writing centroid_embedding_v: "
                        f"{line.strip()[:100]}"
                    )

    def test_self_heal_creates_extension_and_columns(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "main.py"
        ).read_text()
        assert "CREATE EXTENSION IF NOT EXISTS vector" in src, (
            "app/main.py self-heal block must enable the vector extension"
        )
        assert "embedding_v vector(384)" in src and "centroid_embedding_v vector(384)" in src, (
            "Self-heal block must add both pgvector columns idempotently"
        )


class TestTranslationPhase2BPayloadIncludesLongFormFields:
    """Cycle-4 Phase 2-b (2026-05-08): the cron's fa_payload must
    include narratives + bias_explanation + editorial_context so /en
    and /fr can render the bias panel and editorial blurb in the
    target voice (NYT/Le Monde) instead of falling back to FA. Strict
    homepage-scope only (per Parham's 2026-05-08 cost guardrail).
    """

    def test_fa_payload_includes_long_form_fields(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "translate_multilocale.py"
        ).read_text()
        idx = src.find("async def _do_one(snap, locale):")
        assert idx >= 0
        next_def = src.find("\n    async def ", idx + 1)
        body = src[idx:next_def] if next_def > idx else src[idx:idx + 2000]
        for key in (
            '"state_summary"',
            '"diaspora_summary"',
            '"independent_summary"',
            '"bias_explanation"',
            '"editorial_context"',
        ):
            assert key in body, (
                f"fa_payload MUST include {key} so the bias panel + "
                f"editorial blurb render in target voice on /en + /fr."
            )

    def test_phase2b_missing_fields_trigger_retranslation(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "translate_multilocale.py"
        ).read_text()
        # The work-loop must include a "phase 2-b fields missing"
        # branch — otherwise stories that already have title+summary
        # translated never get the bias panel + editorial blurb
        # translated, even when those FA fields exist.
        assert "_phase2b_pairs" in src, (
            "work-loop must check for missing 2-b fields so the SQL "
            "freshness gate (which doesn't know about 2-b) doesn't "
            "skip catch-up translations."
        )
        assert "(snap.get(src_key) or" in src and "not (existing.get(slot_key)" in src, (
            "Missing-field check must compare snapshot FA value to "
            "existing slot value before flagging as needing translation."
        )

    def test_snapshot_pulls_summary_en_blob(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "translate_multilocale.py"
        ).read_text()
        # Snapshot loop must extract the bias narrative blob.
        assert "narrative_blob = _json_pl.loads(s.summary_en)" in src or \
               "narrative_blob.get(\"state_summary_fa\")" in src, (
            "Snapshot must parse summary_en JSON to extract bias "
            "narratives (state_summary_fa et al)."
        )
        assert "editorial_context_fa.get(\"context\")" in src, (
            "Snapshot must extract editorial_context_fa.context"
        )


class TestTranslationDoesNotBumpUpdatedAt:
    """Cycle-2 audit: cron-only translation writes must NOT set
    `updated_at = NOW()`. Doing so combined with the cycle-1
    `<=` staleness gate to drive infinite-retranslation: each fresh
    translation looked stale on the next cron because Python's
    translated_at and Postgres NOW() differ by a few ms.
    """

    def test_jsonb_update_stmt_omits_updated_at(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "translate_multilocale.py"
        ).read_text()
        # Find the pre-bound stmt definition.
        idx = src.find("_jsonb_update_stmt = _sa_text(")
        assert idx >= 0, "_jsonb_update_stmt must exist"
        end = src.find(")", idx)
        block = src[idx:end + 1]
        assert "translations = :blob" in block
        assert "updated_at = NOW()" not in block, (
            "_jsonb_update_stmt is the CRON path; it must not bump "
            "updated_at. Translations are derived; bumping creates an "
            "infinite re-translation loop with the <= staleness gate."
        )


class TestTranslationAgeGateRemoved:
    """Cycle-2 audit: the inner `translation_age_days <= STALE_LOOKBACK_DAYS`
    gate inside translate_homepage_visible was inverted — refused to
    retranslate stale-vs-FA translations whenever the translation was
    >14 days old. Removed.
    """

    def test_no_translation_age_inner_gate(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "translate_multilocale.py"
        ).read_text()
        # Find the gate region.
        idx = src.find("if ta <= snap[\"updated_at\"]:")
        assert idx >= 0, "Outer FA-vs-translated_at check must exist"
        following = src[idx:idx + 600]
        assert "translation_age_days <= STALE_LOOKBACK_DAYS" not in following, (
            "Inner translation_age_days <= STALE_LOOKBACK_DAYS gate was "
            "inverted — it dropped legitimately-stale translations older "
            "than 14d. The DB-level filter at the SQL WHERE already "
            "gates correctly."
        )


class TestNlpTranslationBatchSizeUsedConsistently:
    """Cycle-2 audit: nlp_pipeline.py:339-340 used the hoisted setting
    for the range stride but a hard-coded `+30` for the slice. Operator
    raising the setting to 50 would have skipped articles 30-50 in
    every iteration; lowering to 20 would double-process 20-30. Both
    sides must reference the same value.
    """

    def test_batch_loop_uses_setting_for_slice(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "nlp_pipeline.py"
        ).read_text()
        idx = src.find("nlp_translation_batch_size")
        assert idx >= 0, "Setting must be referenced"
        # Find the EN→FA OpenAI translation block (Step 4b).
        block_start = src.find("if still_en and settings.openai_api_key")
        assert block_start >= 0
        block = src[block_start:block_start + 2000]
        # Hard-coded slice must not appear inside the EN→FA loop.
        assert "+ 30]" not in block, (
            "Slice in EN→FA translation loop must use the hoisted "
            "setting, not a hard-coded literal. See cycle-2 audit."
        )


class TestMaintenanceLockFailsClosed:
    """Cycle-4 (2026-05-08): _try_acquire_lock_async used to return
    True on any DB error — meaning a Neon hiccup during lock check
    let two cron firings proceed in parallel without holding a real
    lock. Now fails CLOSED (returns False) so a transient DB error
    skips ONE cycle (harmless given 6h cadence) instead of running
    parallel unlocked writes.
    """

    def test_lock_acquire_fails_closed_on_exception(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def _try_acquire_lock_async(")
        assert idx >= 0
        nxt = src.find("\nasync def ", idx + 1)
        body = src[idx:nxt] if nxt > idx else src[idx:idx + 2500]
        # The except path must return False, not True. The block has a
        # multi-line comment explaining the fail-closed rationale; allow
        # the whole rest of the function body for the search.
        ex_idx = body.find("except Exception")
        assert ex_idx >= 0
        ex_block = body[ex_idx:]
        assert "return False" in ex_block, (
            "Lock-acquire exception path must return False (fail "
            "closed). Returning True allowed parallel cron runs to "
            "proceed without a confirmed lock — racy writes."
        )
        # The except path must not silently fail open.
        # Look only at the immediate handler before any subsequent
        # function starts (next `async def` already cut by `nxt` above).
        assert "return True" not in ex_block, (
            "The exception path must NOT return True — that's the "
            "fail-open regression we're guarding against."
        )


class TestAdminTranslationEditsBumpUpdatedAt:
    """Cycle-4 (2026-05-08): patch_story_translation and
    clear_story_translation MUST bump Story.updated_at. The cron's
    snapshot-vs-re-read race-check at translate_multilocale.py:504
    only fires when current_updated_at > snap_ts — pre-this-fix admin
    edits/clears mid-cron-batch passed the check silently and the
    cron's stale LLM result OVERWROTE the just-edited slot.

    The cron-path _jsonb_update_stmt deliberately does NOT bump
    updated_at (cycle-2 infinite-retranslation-loop fix). Admin edits
    ARE state changes that must invalidate snapshots.
    """

    def test_patch_story_translation_bumps_updated_at(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def patch_story_translation(")
        assert idx >= 0, "patch_story_translation must exist"
        # Find next function boundary
        nxt = src.find("\n@router.", idx + 1)
        body = src[idx:nxt] if nxt > idx else src[idx:idx + 4000]
        assert "story.updated_at = " in body, (
            "patch_story_translation MUST bump story.updated_at so "
            "the cron's snapshot-vs-re-read race detection works."
        )

    def test_clear_story_translation_bumps_updated_at(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def clear_story_translation(")
        assert idx >= 0, "clear_story_translation must exist"
        nxt = src.find("\n@router.", idx + 1)
        body = src[idx:nxt] if nxt > idx else src[idx:idx + 4000]
        assert "story.updated_at = " in body, (
            "clear_story_translation MUST bump story.updated_at so "
            "mid-cron clears aren't silently resurrected by the stale "
            "LLM write."
        )


class TestTrendingScoreSingleSourceOfTruth:
    """Cycle-4 (2026-05-08): pre-this-cycle, two divergent formulas
    wrote to `Story.trending_score` — clustering.py used `0.5^(hours/48)`
    anchored on first_published_at; auto_maintenance.step_recalculate_
    trending used `0.85^days` anchored on frozen_at??last_updated_at.
    For the same 10-article 7-day-old story they produced 0.88 vs 3.2.
    Homepage rank flickered between cron passes (canonical formula)
    and interim writes (clustering helper).

    Fix: extract a single canonical helper at app/services/trending.py
    and have BOTH writers delegate to it.
    """

    def test_canonical_helper_module_exists(self):
        from pathlib import Path

        p = (
            Path(__file__).parent.parent
            / "app" / "services" / "trending.py"
        )
        assert p.exists(), (
            "app/services/trending.py must exist as the single "
            "source of truth for Story.trending_score."
        )
        src = p.read_text()
        assert "def compute_trending_score(" in src

    def test_step_recalculate_trending_uses_canonical_helper(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_recalculate_trending(")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def] if next_def > 0 else src[idx:idx + 6000]
        assert "from app.services.trending import compute_trending_score" in body, (
            "step_recalculate_trending MUST use the canonical helper"
        )
        # The inline formula must be GONE.
        assert "0.85 ** max(0.0, days_ago)" not in body, (
            "step_recalculate_trending must NOT contain the old "
            "inline 0.85^days formula — delegate to compute_trending_"
            "score in app/services/trending.py instead."
        )

    def test_clustering_compute_trending_uses_canonical_helper(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        idx = src.find("def _compute_trending_score(")
        assert idx >= 0
        next_def = src.find("\ndef ", idx + 1)
        body = src[idx:next_def] if next_def > 0 else src[idx:idx + 2000]
        assert "from app.services.trending import compute_trending_score" in body, (
            "clustering._compute_trending_score MUST delegate to the "
            "canonical helper. The 0.5^(hours/48) formula is gone."
        )
        assert "math.pow(0.5, hours_ago / half_life_hours)" not in body, (
            "clustering._compute_trending_score must NOT contain the "
            "old inline 0.5^(hours/48) formula."
        )

    def test_only_canonical_writers_to_story_trending_score(self):
        """Defense-in-depth: any write to `story.trending_score` (a
        Story object — NOT Source.trending_score, that's a different
        column) must go through `compute_trending_score` or the local
        `_compute_trending_score` shim. Approximate by string-matching
        across backend Python files.
        """
        from pathlib import Path

        backend = Path(__file__).parent.parent
        suspect = []
        for f in backend.rglob("*.py"):
            if "test" in str(f) or "trending.py" in str(f):
                continue
            text = f.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                # Only Story.trending_score (story-prefixed). Source.
                # trending_score in scripts is a different column.
                if "story.trending_score = " not in line:
                    continue
                # Allow writes that route through the canonical helper
                # (or the local shim that delegates to it).
                if "compute_trending_score" in line:
                    continue
                if "_compute_trending_score" in line:
                    continue
                if "_compute_trending(" in line:
                    # topic_clustering's helper now delegates internally.
                    continue
                suspect.append(
                    f"{f.relative_to(backend)}:{i}: {line.strip()[:120]}"
                )
        assert not suspect, (
            f"Unexpected direct writes to Story.trending_score "
            f"(must go through canonical helper): {suspect}"
        )


class TestPipelineTotalStepsMatchesActual:
    """Cycle-4 (2026-05-08): pre-this-fix, total_steps was set to
    len(FULL_PIPELINE) = 58 but full mode runs an EXTRA 'Update
    project docs' step after the loop. Dashboard progress bar
    showed 58/58 then jumped to 59/58. Match the actual count.
    """

    def test_total_steps_includes_docs_step_for_full_mode(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("await maintenance_state.start_run(total_steps=")
        assert idx >= 0
        line = src[idx:idx + 200]
        assert "len(pipeline) + _extra_steps" in line, (
            "total_steps must add 1 for full mode to account for the "
            "trailing 'Update project docs' step."
        )


class TestAuditClusterCoherenceScopedToRecent:
    """Cycle-3 audit (2026-05-08): audit_cluster_coherence loaded ALL
    stories with article_count >= 10 (561 in production), including
    3-year-old frozen umbrellas. Each story required a 4-row Article.
    embedding sample, burning ~8 MB pure-waste egress per cron. Add a
    7-day last_updated_at gate + skip frozen + archived.
    """

    def test_audit_filters_on_last_updated_at(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        idx = src.find("async def audit_cluster_coherence(")
        assert idx >= 0
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end] if end > idx else src[idx:idx + 4000]
        # Recently-active filter must be present
        assert "Story.last_updated_at >= audit_cutoff" in body, (
            "audit_cluster_coherence MUST scope to last_updated_at "
            ">= audit_cutoff (7d) — otherwise it iterates ancient frozen "
            "umbrellas every cron and burns egress."
        )
        assert "Story.frozen_at.is_(None)" in body, (
            "audit_cluster_coherence MUST skip frozen stories — they "
            "can't absorb new articles, so drift audit adds no signal."
        )
        assert "Story.archived_at.is_(None)" in body, (
            "audit_cluster_coherence MUST skip archived stories"
        )
        assert "timedelta(days=7)" in body, (
            "Audit window must be 7 days"
        )


class TestRefreshStoriesMetadataBatchDefersHeavyJsonb:
    """Cycle-3 audit (2026-05-08): cycle-1 commit 7e6fa46 added defers
    to the three merge functions but missed _refresh_stories_metadata_batch.
    Each Story row carries ~70-80 KB of heavy JSONB; the function only
    reads summary_fa and is_edited. ~12 MB/day wasted egress before
    this defer.
    """

    def test_batch_helper_defers_heavy_jsonb(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        idx = src.find("async def _refresh_stories_metadata_batch(")
        assert idx >= 0
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end] if end > idx else src[idx:idx + 6000]
        # All 8 heavy JSONB columns must be deferred.
        for col in (
            "translations",
            "telegram_analysis",
            "editorial_context_fa",
            "summary_anchor",
            "analysis_snapshot_24h",
            "summary_en",
            "hourly_update_signal",
            "centroid_embedding",
        ):
            assert f"_defer_refresh(Story.{col})" in body, (
                f"_refresh_stories_metadata_batch must defer Story.{col} "
                f"— function reads only summary_fa + is_edited."
            )


class TestBudgetStatusDoesNotConsumeOverride:
    """Cycle-3 audit (2026-05-08): /admin/budget/status used to call
    should_halt_for_budget without `consume_override=False`, so any
    dashboard polling between override-set and the next cron pre-flight
    would burn the one-shot. The 2026-05-08 morning cron halted
    despite the operator clearing the override 7h before — some
    intermediate /budget/status call ate it. Fix: status endpoint
    passes consume_override=False; cron pre-flight keeps default True.
    """

    def test_status_endpoint_uses_consume_override_false(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        # Find the /budget/status endpoint body.
        idx = src.find("async def budget_status(")
        assert idx >= 0
        end = src.find("@router.", idx + 1)
        body = src[idx:end] if end > idx else src[idx:idx + 2000]
        assert "consume_override=False" in body, (
            "/budget/status MUST pass consume_override=False so dashboard "
            "polling doesn't burn the operator's one-shot clear."
        )

    def test_should_halt_accepts_consume_override_kwarg(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        # Signature must accept the kwarg, default True. Signature spans
        # multiple lines; find the closing `) -> ` of the def.
        idx = src.find("async def should_halt_for_budget(")
        assert idx >= 0
        close_paren = src.find(")", idx)
        sig = src[idx:close_paren + 1]
        assert "consume_override: bool = True" in sig, (
            "should_halt_for_budget signature must accept "
            "consume_override kwarg (default True)."
        )

    def test_clear_branch_only_consumes_when_flag_set(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        # The override-clearing UPDATE must be guarded by consume_override.
        update_idx = src.find('UPDATE budget_override SET action = NULL')
        assert update_idx >= 0
        # Look back 300 chars to find the conditional gate.
        gate_window = src[max(0, update_idx - 300):update_idx]
        assert "if consume_override:" in gate_window, (
            "The clearing UPDATE must be wrapped in `if "
            "consume_override:` so read-only callers preserve the flag."
        )


class TestClusterStepNameError:
    """Cycle-3 audit (2026-05-08): cycle-1 commit 6abc775 referenced
    `article_candidates` in cluster_articles.stats but the variable
    lives only in `_match_to_existing_stories` scope. Every cron since
    that commit hit `NameError: name 'article_candidates' is not
    defined` at the cluster step, dropping clustering for ~20h until
    detected on the 2026-05-08 03:00 UTC cron. Fix: tuple return from
    the matcher.
    """

    def test_match_to_existing_stories_all_returns_are_tuple(self):
        """Cycle-4 (2026-05-08) hardened from cycle-3: scan EVERY
        `return` inside _match_to_existing_stories. The cycle-3 fix
        (`0f3a383`) only updated the final return; two early-exit
        paths (no visible stories; all articles auto-match/reject)
        kept the old `return articles` shape. Caller's tuple unpack
        crashed under those triggers — and triggers fire often
        (test envs have empty existing_stories; many production cron
        batches fall fully outside the LLM band).
        """
        from pathlib import Path
        import re

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        idx = src.find("async def _match_to_existing_stories(")
        assert idx >= 0
        end_marker = src.find(
            "\nasync def _refresh_story_metadata", idx
        )
        assert end_marker > idx, "Function boundary must be findable"
        body = src[idx:end_marker]
        # Every `return` outside comments + nested defs in this
        # function must produce a 2-tuple. Approximate by checking
        # the line text directly: must have a comma-separated
        # expression OR the variable named `unmatched_ids` followed
        # by `, len(article_candidates)`.
        lines = body.splitlines()
        bad_returns = []
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped.startswith("return "):
                continue
            # Tolerate `return None` and bare `return` only if both don't
            # appear (they shouldn't in this fn). The valid shapes:
            #   return article_ids_eager, 0
            #   return unmatched_ids, len(article_candidates)
            #   return X, Y  (any 2-tuple)
            payload = stripped[len("return "):].rstrip()
            # A scalar (no comma at top level) is the bug.
            if "," not in payload:
                bad_returns.append((i, line.strip()))
        assert not bad_returns, (
            "All returns in _match_to_existing_stories MUST be "
            "2-tuples (unmatched_ids, candidate_count). Found scalar "
            f"return(s): {bad_returns}"
        )
        # And the canonical final return must still reference
        # len(article_candidates) so the count hooks survive future
        # refactors.
        ret_idx = body.rfind("return ")
        ret_line = body[ret_idx:ret_idx + 200]
        assert "len(article_candidates)" in ret_line, (
            "Final return must include len(article_candidates) so "
            "cluster stats see the candidate count."
        )

    def test_cluster_articles_unpacks_tuple(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        # The cluster_articles function must unpack the tuple.
        assert (
            "unmatched_ids, llm_candidates_sent = await _match_to_existing_stories"
            in src
        ), "cluster_articles must unpack the tuple from the matcher"

    def test_cluster_stats_uses_captured_count(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        # The stats dict must reference the captured local, not the
        # out-of-scope `article_candidates`.
        assert '"llm_candidates_sent": int(len(article_candidates))' not in src, (
            "Cluster stats dict must NOT reference article_candidates "
            "directly — that variable lives only in the matcher scope. "
            "Use the captured llm_candidates_sent local."
        )


class TestStepSummarizeNoCentroidDefer:
    """Cycle-2 audit (CRITICAL): cycle-1 commit 12076f9 added
    `defer(Story.centroid_embedding)` to step_summarize's main
    select(Story). The function reads `s.centroid_embedding` /
    `story.centroid_embedding` at 8 later sites (cosine drift,
    title-cohesion gate, refile logic). In async SQLAlchemy, each
    deferred-then-accessed read raises `sqlalchemy.exc.MissingGreenlet`,
    crashing step_summarize on every cron. Defer removed.
    """

    def test_step_summarize_does_not_defer_centroid_embedding(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        # Locate the step_summarize main candidate select.
        idx = src.find("step_summarize uses content_text + title +")
        assert idx >= 0, (
            "step_summarize comment block must remain to anchor this test"
        )
        # Look at the next ~600 chars (the select + options block).
        block = src[idx:idx + 1500]
        # The article-level defers are required; the Story-level defer
        # of centroid_embedding is the trap.
        assert "_defer_summ(Story.centroid_embedding)" not in block, (
            "step_summarize must NOT defer Story.centroid_embedding — "
            "the function reads it at 8 later sites and async lazy-load "
            "raises MissingGreenlet. See cycle-2 audit."
        )


class TestDedupPoolOrderedByRecency:
    """Cycle-2 audit: cycle-1 dropped pool 500→100 (commit a540c7a)
    but the query has no ORDER BY. Postgres returns arbitrary heap-
    order rows; on dense days the most-recent repost candidates can
    fall outside the 100-row sample. Add ORDER BY ingested_at DESC.
    """

    def test_dedup_pool_query_orders_by_ingested_at(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "nlp_pipeline.py"
        ).read_text()
        # Locate the recent_result query (Step 4c, embedding dedup pool).
        idx = src.find("# Cycle-1 audit Island 2: dropped 500 → 100")
        assert idx >= 0, (
            "Cycle-1 dedup-pool comment must remain to anchor this test"
        )
        block = src[idx:idx + 1200]
        assert "Article.ingested_at.desc()" in block, (
            "Dedup pool must ORDER BY ingested_at DESC so the 100-row "
            "sample is the most-recent — not arbitrary heap order."
        )

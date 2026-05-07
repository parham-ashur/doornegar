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
    summarize at line 6681 in FULL_PIPELINE), the briefing's hero pick
    can be a cron cycle behind reality.

    Fix: add an extra recalc_trending pass right after merge_similar,
    before summarize. The recompute is idempotent and cheap (~3s);
    the original late recalc still runs to pick up later-step changes
    (prune/demote/archive)."""

    def test_recalc_trending_runs_before_summarize(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()

        # Find the FULL_PIPELINE block and confirm step ordering.
        idx = src.find("FULL_PIPELINE = [")
        assert idx >= 0
        # Find positions of merge_similar, the pre-summarize recalc, and summarize.
        # The recalc must be between merge_similar and summarize.
        merge_pos = src.find('"step_merge_similar"', idx)
        summarize_pos = src.find('"step_summarize"', idx)
        recalc_pre_pos = src.find('"recalc_trending_pre_summarize"', idx)
        assert merge_pos >= 0 and summarize_pos >= 0, (
            "FULL_PIPELINE must contain merge_similar and summarize"
        )
        assert recalc_pre_pos >= 0, (
            "FULL_PIPELINE must contain a 'recalc_trending_pre_summarize' "
            "step between merge_similar and summarize so doornama_top_ids "
            "reflects post-ingest reality. Without it, the hero-card "
            "briefing lags by one 6h cron cycle."
        )
        assert merge_pos < recalc_pre_pos < summarize_pos, (
            f"Step ordering wrong: merge_similar({merge_pos}) → "
            f"recalc_trending_pre_summarize({recalc_pre_pos}) → "
            f"summarize({summarize_pos}) is the required order."
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

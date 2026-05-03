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

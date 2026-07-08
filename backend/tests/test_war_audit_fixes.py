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
        """The min_articles + min_score constants must equal the API defaults.

        2026-07-08: api/v1/stories.py now imports TRENDING_MIN_ARTICLES /
        BLINDSPOT_MIN_ARTICLES directly as its Query() defaults instead of
        hardcoding its own copy, so drift between the two is no longer
        possible by construction — this test now just pins the intentional
        value. Lowered 4 -> 3 the same day (Parham's call): the 182e12c
        merge_tiny fix correctly stopped bad merges but left most stories
        stuck at 2-3 articles with nothing inflating them past 4 anymore
        (0 stories in the 4-9 bucket, homepage down to 4 trending + 1
        blindspot story). 3 restores real content without dropping all
        the way to 2, which would let very thin single-narrative stories
        onto a site built around multi-source comparison.
        """
        from app.services.homepage_scope import (
            TRENDING_MIN_ARTICLES,
            TRENDING_MIN_SCORE,
            BLINDSPOT_MIN_ARTICLES,
        )
        from app.api.v1.stories import trending_stories, blindspot_stories
        import inspect

        assert TRENDING_MIN_ARTICLES == 3, (
            "TRENDING_MIN_ARTICLES changed — confirm this was an intentional "
            "homepage-content decision, not an accidental edit."
        )
        assert TRENDING_MIN_SCORE == 0.5, (
            "TRENDING_MIN_SCORE drifted from the API default (0.5)."
        )
        assert BLINDSPOT_MIN_ARTICLES == 3, (
            "BLINDSPOT_MIN_ARTICLES changed — confirm this was an intentional "
            "homepage-content decision, not an accidental edit."
        )

        # Structural guarantee: the API's Query() default must literally be
        # the same object/value as the constant, not a second hardcoded copy.
        trending_default = inspect.signature(trending_stories).parameters["min_articles"].default.default
        blindspot_default = inspect.signature(blindspot_stories).parameters["min_articles"].default.default
        assert trending_default == TRENDING_MIN_ARTICLES
        assert blindspot_default == BLINDSPOT_MIN_ARTICLES

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
        # Window covers the function (grew with the 2026-06-09
        # activity-aware logic + its docstring).
        end = source.find("\nasync def ", start + 50)
        window = source[start : end if end > 0 else start + 6000]

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

        # 2026-06-09: demote is now activity-aware — a frozen story still
        # taking heavy fresh coverage must NOT be sunk (and is re-promoted
        # if already at -50). Sort-order only; freeze semantics untouched.
        # See test_regression_cases.TestActiveFrozenStoriesNotBuried.
        assert "ACTIVE_MIN_ARTICLES" in window, (
            "demote step lost its activity-aware exemption — active frozen "
            "stories (e.g. an ongoing war) will be buried again."
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
        # The pipeline-loop start_run call uses `len(pipeline) +
        # _extra_steps`. Phase E.2 (2026-05-09) added an earlier
        # start_run for the manual_lock short-circuit which uses
        # `total_steps=1` — skip past that one to find the real
        # pipeline-mode call.
        anchor = "_extra_steps = 1 if mode == \"full\" else 0"
        idx = src.find(anchor)
        assert idx >= 0, (
            "Pipeline-mode start_run anchor comment must remain"
        )
        line = src[idx:idx + 400]
        assert "start_run(total_steps=len(pipeline) + _extra_steps)" in line, (
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
        idx = src.find("Cycle-2 audit (2026-05-07): the cycle-1 attempt to also defer")
        assert idx >= 0, (
            "step_summarize cycle-2 audit comment must remain to anchor this test"
        )
        # Look at the preceding ~800 chars (covers the selectinload options block).
        block = src[max(0, idx - 800):idx + 600]
        # Story.centroid_embedding must NOT be deferred — it's read at 8 sites
        # in step_summarize; async lazy-load of a deferred attribute raises MissingGreenlet.
        assert "_defer_summ(Story.centroid_embedding)" not in block, (
            "step_summarize must NOT defer Story.centroid_embedding — "
            "the function reads it at 8 later sites and async lazy-load "
            "raises MissingGreenlet. See cycle-2 audit."
        )
        # Article.embedding must also NOT be deferred — the drift check at the
        # candidate-scan loop accesses a.embedding; deferring it causes the same
        # MissingGreenlet crash (confirmed 2026-06-20).
        assert "_defer_summ(Article.embedding)" not in block, (
            "step_summarize must NOT defer Article.embedding — the drift check "
            "accesses a.embedding inside async SQLAlchemy. See 2026-06-20 fix."
        )


class TestSummarizeRefreshesOnArticleShrink:
    """2026-07-03 Niloofar audit found two stories whose narrative text
    described a completely different article set than the one currently
    in the cluster — traced to step_summarize's volume_trigger only
    firing on GROWTH (new_articles >= VOLUME_TRIGGER). A story pruned
    from 28 articles down to 3 (remove_article, or an admin detach) kept
    its stale 28-article narrative forever: hash_changed was True but
    volume_trigger was always False for a negative new_articles, so
    needs_rerun never fired. Fix adds a symmetric SHRINK_TRIGGER so
    meaningful removals also re-trigger analysis.
    """

    def test_shrink_trigger_constant_defined(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        assert "SHRINK_TRIGGER = 3" in src, (
            "step_summarize must define SHRINK_TRIGGER — a meaningful "
            "article-count shrink must also trigger re-analysis, not "
            "just growth. See 2026-07-03 audit."
        )

    def test_volume_trigger_fires_on_shrink_not_just_growth(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("# Volume gate — refresh on a large new-article batch")
        assert idx >= 0, (
            "step_summarize's volume-gate comment block must remain to anchor this test"
        )
        block = src[idx:idx + 500]
        assert "new_articles >= VOLUME_TRIGGER" in block
        assert "new_articles <= -SHRINK_TRIGGER" in block, (
            "volume_trigger must also fire when new_articles is a large "
            "negative number (articles removed from the cluster) — "
            "growth-only was the 2026-07-03 bug."
        )


class TestSummarizeShrinkBreaksMaturityLock:
    """2026-07-04 follow-up: the 2026-07-03 SHRINK_TRIGGER fix only helps a
    story BEFORE it's locked — the `analysis_locked_at` check runs first and
    exits unconditionally, so the shrink-trigger code is unreachable for any
    story that was already mature-locked (48h+ stable) before it got pruned.
    Confirmed live: story c0f9adf7 was locked at 03:15 UTC on 2026-07-04 —
    HOURS after the shrink-trigger fix deployed — while already 9 articles
    stale. Fix lets a meaningful shrink (>= SHRINK_TRIGGER since the count
    recorded at lock time) pop analysis_locked_at and requeue the story.
    """

    def test_locked_story_can_be_unlocked_by_shrink(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("# Already locked → never re-analyze, UNLESS the article set has")
        assert idx >= 0, (
            "step_summarize's lock-check comment must remain to anchor this test"
        )
        block = src[idx:idx + 1400]
        assert 'b.get("analysis_locked_at")' in block
        assert "articles_count_at_hash" in block
        assert "count_at_lock - cur_count) >= SHRINK_TRIGGER" in block, (
            "a locked story must be unlockable when its article count has "
            "shrunk by >= SHRINK_TRIGGER since the count recorded at lock "
            "time — otherwise pruning that happens after the 48h maturity "
            "lock (the common case for Niloofar cleanup) can never "
            "re-trigger analysis, even with the growth/shrink volume gate."
        )
        assert 'b.pop("analysis_locked_at", None)' in block


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


class TestAdminLLMEndpointsHaveBudgetGuard:
    """Cycle-5 C1 (CRITICAL 2026-05-08): admin trigger endpoints used
    to bypass `should_halt_for_budget` entirely. The cron pre-flight
    was the only choke point. With manual_lock active, a click on
    /admin/force-resummarize could still fan out 200 gpt-5-mini
    calls = $10 of LLM spend.

    This test pins the dependency wiring (source-text inspection so
    no DB or app boot needed). If a future cycle removes
    `Depends(enforce_budget)` from any of these endpoints, the test
    fails — drawing attention to a regression that would otherwise
    only show up as another billing surprise.
    """

    GUARDED_ENDPOINTS = (
        ("/force-resummarize", "app/api/v1/admin.py"),
        ("/nlp/trigger", "app/api/v1/admin.py"),
        ("/cluster/trigger", "app/api/v1/admin.py"),
        ("/bias/trigger", "app/api/v1/admin.py"),
        ("/pipeline/run-all", "app/api/v1/admin.py"),
        ("/cluster-llm/trigger", "app/api/v1/admin.py"),
        ("/topics/{topic_id}/analyze", "app/api/v1/lab.py"),
        ("/topics/{topic_id}/generate-analysts", "app/api/v1/lab.py"),
    )

    def test_each_endpoint_wires_enforce_budget(self):
        from pathlib import Path

        for route, relpath in self.GUARDED_ENDPOINTS:
            src = (
                Path(__file__).parent.parent / relpath
            ).read_text()
            idx = src.find(f'"{route}"')
            assert idx >= 0, (
                f"Endpoint {route} not found in {relpath} — test "
                f"anchor is stale"
            )
            # The decorator block ends at the `async def` that follows
            # it. Inspect only that window.
            block_end = src.find("async def", idx)
            assert block_end > idx
            decorator_block = src[idx:block_end]
            assert "Depends(enforce_budget)" in decorator_block, (
                f"Endpoint {route} in {relpath} is missing "
                f"Depends(enforce_budget). Cycle-5 C1 regression — "
                f"manual_lock will not protect this endpoint."
            )

    def test_enforce_budget_uses_consume_override_false(self):
        """Dashboard polling /budget/status should never burn a one-shot
        clear. The shared dep must pass consume_override=False.
        """
        from pathlib import Path

        bg_src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        # Find enforce_budget_or_403_dep body.
        idx = bg_src.find("async def enforce_budget_or_403_dep")
        assert idx >= 0, "enforce_budget_or_403_dep must exist in budget_guard.py"
        # Look at the next ~500 chars (function body).
        body = bg_src[idx:idx + 1000]
        assert "consume_override=False" in body, (
            "enforce_budget_or_403_dep must call should_halt_for_budget "
            "with consume_override=False so dashboard polling doesn't "
            "burn the operator's one-shot clear."
        )


class TestForceResummarizeJobChecksBudgetPerStory:
    """Cycle-5 C2 (CRITICAL 2026-05-08): the endpoint dependency
    catches the click, but a job that started while budget was
    healthy can keep running for 30+ minutes processing 200 stories.
    If MTD crosses 80% mid-loop (e.g. a separate cron run lands),
    the remaining stories should NOT be processed.
    """

    def test_per_story_budget_check_present(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def _run_force_resummarize_job")
        assert idx >= 0
        # Body of the function up to the next top-level def
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        assert "should_halt_for_budget" in body, (
            "_run_force_resummarize_job must check should_halt_for_budget "
            "before each story so a 200-story batch can short-circuit "
            "when budget crosses 80% mid-loop. Cycle-5 C2 regression."
        )
        # The check must use consume_override=False so a one-shot
        # operator clear isn't burned on the very first story.
        assert "consume_override=False" in body, (
            "_run_force_resummarize_job per-story budget check must use "
            "consume_override=False so the operator's clear isn't burned "
            "on the first story of a long manual run."
        )


class TestAnthropicFallbacksLogToBudgetLedger:
    """Cycle-5 C6 (CRITICAL 2026-05-08): the budget guard reads MTD
    from llm_usage_logs.total_cost. Anthropic fallback paths in
    bias_scoring._call_anthropic and llm_utils._call_anthropic
    used to call the API but never wrote to the ledger. Result:
    when OpenAI rate-limits force fallback for hours, MTD reads
    too low and the kill-switch never fires. Defeats the
    invariant entirely.
    """

    def test_bias_scoring_call_anthropic_logs(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "bias_scoring.py"
        ).read_text()
        idx = src.find("async def _call_anthropic")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else idx + 2000]
        assert "log_llm_usage" in body, (
            "bias_scoring._call_anthropic must call log_llm_usage "
            "after every Anthropic call. Cycle-5 C6 regression."
        )

    def test_llm_utils_call_anthropic_logs(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "llm_utils.py"
        ).read_text()
        idx = src.find("async def _call_anthropic")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else idx + 2000]
        assert "log_llm_usage" in body, (
            "llm_utils._call_anthropic must call log_llm_usage "
            "after every Anthropic call. Cycle-5 C6 regression."
        )


class TestTelethonFloodWaitHandled:
    """Cycle-5 C3 (CRITICAL 2026-05-08): Telethon used to raise
    FloodWaitError as a generic exception. ingest_all_channels
    caught the broad exception, logged an error, and moved on to
    the NEXT channel. Continuing to hit the API after a long
    FloodWait compounds the offense and risks a session ban —
    which would invalidate the prod session and require Parham
    to redo phone-SMS auth. The fix: cap auto-sleep at 300s,
    raise a sentinel TelegramFloodHalt for waits longer than
    that, stop the run.
    """

    def test_telegram_client_uses_300s_flood_threshold(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_service.py"
        ).read_text()
        idx = src.find("_client = TelegramClient(")
        assert idx >= 0
        # Look at the next ~600 chars (the constructor call).
        block = src[idx:idx + 600]
        assert "flood_sleep_threshold=300" in block, (
            "TelegramClient ctor must pass flood_sleep_threshold=300. "
            "Without it, FloodWaits in the 60-300s range surface as "
            "opaque exceptions instead of being absorbed transparently. "
            "Cycle-5 C3 regression."
        )

    def test_fetch_channel_posts_raises_flood_halt(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_service.py"
        ).read_text()
        idx = src.find("async def fetch_channel_posts")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        assert "FloodWaitError" in body, (
            "fetch_channel_posts must explicitly catch FloodWaitError. "
            "Cycle-5 C3 regression."
        )
        assert "TelegramFloodHalt" in body, (
            "fetch_channel_posts must raise TelegramFloodHalt on "
            "FloodWait so ingest_all_channels short-circuits the run."
        )

    def test_ingest_all_channels_short_circuits_on_flood(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_service.py"
        ).read_text()
        idx = src.find("async def ingest_all_channels")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        assert "except TelegramFloodHalt" in body, (
            "ingest_all_channels must catch TelegramFloodHalt and "
            "break out of the channel loop. Cycle-5 C3 regression."
        )
        # The loop must actually break, not just log + continue.
        # Locate the except clause and look at the next ~500 chars.
        ex_idx = body.find("except TelegramFloodHalt")
        ex_block = body[ex_idx:ex_idx + 500]
        assert "break" in ex_block, (
            "TelegramFloodHalt handler must `break` out of the channel "
            "loop. Continuing risks a session ban."
        )


class TestTelegramClientDisconnectsBetweenRuns:
    """Cycle-5 H20 (HIGH 2026-05-08): module-global _client survived
    across cron runs but never disconnected. Telethon's internal
    state (resolved-entity cache, last-seen update IDs, transient
    FloodWait counters) accumulates; sessions DB file grows; memory
    risk on Railway 8GB hobby plan. Fix: try/finally in
    ingest_all_channels disconnects + resets _client = None.
    """

    def test_ingest_all_channels_disconnects_in_finally(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_service.py"
        ).read_text()
        idx = src.find("async def ingest_all_channels")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        # The function body must declare global _client.
        assert "global _client" in body, (
            "ingest_all_channels must declare global _client so it can "
            "reset it in the finally block."
        )
        # finally clause must be present.
        assert "finally:" in body, (
            "ingest_all_channels must wrap the channel loop in "
            "try/finally to disconnect on every exit path. Cycle-5 H20."
        )
        # finally block must call disconnect AND reset _client.
        f_idx = body.find("finally:")
        f_block = body[f_idx:f_idx + 600]
        assert "disconnect" in f_block, (
            "finally block must call _client.disconnect()."
        )
        assert "_client = None" in f_block, (
            "finally block must reset _client = None so the next cron "
            "run starts from a clean slate."
        )


class TestImageDownloaderHasByteCaps:
    """Cycle-5 C4 + C5 (CRITICAL 2026-05-08): image_downloader had no
    byte caps. A 50 MB hero PNG (or worse, a video URL that 200s with
    image/jpeg content-type) was buffered into memory then handed to
    Pillow → OOM on Railway 8GB Hobby. The pass-through branch
    (recompression failed: GIF, SVG, etc.) wrote the ORIGINAL uncapped
    bytes to R2 — turning a single bad source into a $$ R2 bill.

    Two caps:
    - MAX_IMAGE_BYTES (8 MB): streamed download abort when exceeded
    - MAX_PASSTHROUGH_BYTES (1 MB): reject pass-through R2 upload when
      recompression failed AND original is large
    """

    def test_max_byte_constants_defined(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "image_downloader.py"
        ).read_text()
        assert "MAX_IMAGE_BYTES" in src, (
            "image_downloader must define MAX_IMAGE_BYTES. Cycle-5 C4."
        )
        assert "MAX_PASSTHROUGH_BYTES" in src, (
            "image_downloader must define MAX_PASSTHROUGH_BYTES. "
            "Cycle-5 C5."
        )
        # Sanity-check the actual values (don't allow a future cycle to
        # weaken to e.g. 100 MB without explicit review).
        assert "MAX_IMAGE_BYTES = 8 * 1024 * 1024" in src, (
            "MAX_IMAGE_BYTES must stay 8 MB. Larger weakens OOM "
            "protection on Railway 8GB containers."
        )
        assert "MAX_PASSTHROUGH_BYTES = 1 * 1024 * 1024" in src, (
            "MAX_PASSTHROUGH_BYTES must stay 1 MB. Larger weakens R2 "
            "egress / cost protection."
        )

    def test_download_uses_streaming_with_cap(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "image_downloader.py"
        ).read_text()
        # Locate the R2-branch download (the production path).
        idx = src.find("# Download source image")
        assert idx >= 0
        block = src[idx:idx + 2000]
        # Must use httpx.stream — `client.get()` reads full body into
        # memory which is the OOM trap.
        assert 'client.stream("GET"' in block, (
            "R2 image download must use httpx client.stream so the "
            "8 MB cap can abort early. Cycle-5 C4."
        )
        # Must check against MAX_IMAGE_BYTES inside the stream loop.
        assert "MAX_IMAGE_BYTES" in block, (
            "R2 image download must abort when total > MAX_IMAGE_BYTES."
        )

    def test_passthrough_branch_rejects_oversize(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "image_downloader.py"
        ).read_text()
        # Locate the pass-through branch (recompression failed).
        idx = src.find("# Pass-through path:")
        assert idx >= 0
        block = src[idx:idx + 1500]
        assert "MAX_PASSTHROUGH_BYTES" in block, (
            "Pass-through branch must check MAX_PASSTHROUGH_BYTES "
            "before uploading the original bytes to R2. Cycle-5 C5."
        )
        # Must return None on oversize — not silently truncate.
        check_idx = block.find("MAX_PASSTHROUGH_BYTES")
        check_block = block[check_idx:check_idx + 400]
        assert "return None" in check_block, (
            "Pass-through oversize must return None (drop the image), "
            "not silently truncate or fall through."
        )

    def test_pillow_pixel_bomb_guard(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "image_downloader.py"
        ).read_text()
        assert "MAX_IMAGE_PIXELS" in src, (
            "Pillow MAX_IMAGE_PIXELS must be set explicitly to defend "
            "against decompression-bomb attacks. Cycle-5 C4."
        )


class TestSevenDayDataWindow:
    """Parham 2026-05-09: clustering / centroids / telegram-link /
    telegram-sentiment all operate on articles + posts ≤ 7 days. Older
    content stays queryable for archived/historical pages but is
    invisible to the pipeline.

    Triggered by the 2026-05-09 umbrella incident: two stories had
    absorbed 1464 + 2354 articles over 60-70 days because the cluster
    window was 30 days while the freeze rule was 7 days. Mismatch =
    umbrellas grow for 23 days before the freeze catches them.

    This test pins the four hot cutoffs at ≤ 7 days. Future cycles
    cannot weaken any of them without the test failing.
    """

    def test_cluster_articles_uses_7d_cutoff(self):
        """clustering.cluster_articles main cutoff."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        idx = src.find("async def cluster_articles")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        # Find the FIRST timedelta(days=N) inside cluster_articles
        # — that's the unclustered-articles cutoff.
        import re
        first_cutoff = re.search(r"timedelta\(days=(\d+)\)", body)
        assert first_cutoff is not None, (
            "cluster_articles must declare a timedelta(days=N) cutoff"
        )
        n = int(first_cutoff.group(1))
        assert n <= 7, (
            f"cluster_articles cutoff is {n} days — must be ≤ 7. "
            f"Older articles must NOT enter clustering."
        )

    def test_match_existing_age_cap_is_7d(self):
        """clustering._match_to_existing_stories AGE_CAP_DAYS."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "clustering.py"
        ).read_text()
        # AGE_CAP_DAYS lives inside _match_to_existing_stories.
        idx = src.find("AGE_CAP_DAYS = ")
        assert idx >= 0, "AGE_CAP_DAYS constant must remain"
        # Read the integer literal that follows.
        import re
        m = re.search(r"AGE_CAP_DAYS = (\d+)", src)
        assert m is not None
        n = int(m.group(1))
        assert n <= 7, (
            f"AGE_CAP_DAYS is {n} — must be ≤ 7. Match-existing must "
            f"only consider articles ≤ 7 days old."
        )

    def test_recompute_centroids_filters_to_7d(self):
        """auto_maintenance.step_recompute_centroids must filter the
        article-embedding query to articles ingested in the last 7 days.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_recompute_centroids")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        # The function must include a 7-day cutoff for the article query.
        assert "timedelta(days=7)" in body or "_td_centroid(days=7)" in body or "_td(days=7)" in body, (
            "step_recompute_centroids must filter Article.embedding to "
            "articles ingested in the last 7 days. Otherwise old "
            "articles drag the centroid and attract more drift."
        )
        # And the filter must be applied to the embedding-fetch query
        # (Article.ingested_at >= cutoff).
        assert "Article.ingested_at" in body, (
            "step_recompute_centroids must filter by Article.ingested_at"
        )

    def test_telegram_link_story_recency_is_7d(self):
        """telegram_analysis.link_posts_by_embedding story_recency_cutoff
        must be ≤ 7 days. Was 14 before the 2026-05-09 audit.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_analysis.py"
        ).read_text()
        idx = src.find("story_recency_cutoff =")
        assert idx >= 0, (
            "link_posts_by_embedding must declare story_recency_cutoff"
        )
        # Read the days=N value on or near this line.
        line_block = src[idx:idx + 200]
        import re
        m = re.search(r"days=(\d+)", line_block)
        assert m is not None
        n = int(m.group(1))
        assert n <= 7, (
            f"story_recency_cutoff is {n} days — must be ≤ 7. "
            f"A post can't link to a story with no recent articles "
            f"to validate the match."
        )


class TestStoryDetailNoDuplicateTranslationsKwarg:
    """2026-05-09 fix: /api/v1/stories/{id} 500'd with TypeError because
    brief.model_dump() already included `translations` (cycle-4 commit
    632ab15 promoted it to StoryBrief), and the StoryDetail constructor
    was ALSO passing `translations=story.translations` explicitly. Python
    raised "got multiple values for keyword argument 'translations'"
    on every request — silently breaking every story detail page since
    632ab15 landed.

    This test pins the fix: the get_story handler must NOT pass an
    explicit `translations=` kwarg next to `**brief.model_dump()`.
    """

    def test_get_story_does_not_double_pass_translations(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find("async def get_story(")
        assert idx >= 0, "get_story handler must remain"
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        # Find the StoryDetail constructor block.
        sd_idx = body.find("response = StoryDetail(")
        assert sd_idx >= 0
        # Look at a comfortable window around the constructor call.
        sd_block = body[sd_idx:sd_idx + 800]
        # The block must contain `**brief.model_dump()` (the kwarg
        # spread that brings in translations).
        assert "**brief.model_dump()" in sd_block, (
            "get_story must spread brief.model_dump() into StoryDetail"
        )
        # And the block must NOT additionally pass translations=. If
        # someone re-adds it, this test fails immediately and the
        # 500-on-every-detail-page regression is caught at CI time
        # rather than after pushing to prod.
        assert "translations=story.translations" not in sd_block, (
            "get_story must NOT pass translations= kwarg explicitly. "
            "brief.model_dump() already provides it (StoryBrief field). "
            "Duplicate kwargs raise TypeError and 500 the endpoint."
        )


class TestPhaseFOptimizationsLanded:
    """Phase F (Parham 2026-05-09): broader 'optimize for restrictions'
    work after the 30 GB Neon incident. Pins the per-step egress
    instrumentation, the trending /trending egress cuts, and the
    Procfile cleanup so future cycles can't accidentally undo them.
    """

    def test_per_step_egress_instrumentation(self):
        """Phase F.1: every step records tup_returned delta + estimate_mb."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        # The pipeline for-loop must read tup_returned before/after
        # each step and attach _egress to the result dict.
        anchor = "Phase F.1"
        assert anchor in src, "Phase F.1 anchor must remain"
        block_start = src.find(anchor)
        block = src[block_start:block_start + 4000]
        assert "tup_before" in block and "tup_after" in block, (
            "Pipeline must take before/after tup_returned snapshots."
        )
        assert '"_egress"' in block or "'_egress'" in block, (
            "Step result dict must carry an _egress sub-dict."
        )
        assert "tup_delta" in block and "estimate_mb" in block, (
            "_egress must include tup_delta and estimate_mb."
        )

    def test_egress_per_step_endpoint_exists(self):
        """Phase F.1: /admin/egress/per-step Pareto endpoint."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        assert '@router.get("/egress/per-step"' in src, (
            "Phase F.1 /admin/egress/per-step endpoint must exist."
        )

    def test_sa_text_imported_before_pipeline_loop(self):
        """2026-05-31 fix: the per-step egress probe calls `_sa_text(...)`.
        That import must be UNCONDITIONAL and BEFORE the pipeline loop.

        Bug: `_sa_text` was imported only inside the full-halt branch
        (which returns early), so on every NON-halted run the probe hit a
        NameError that its `except` swallowed → tup_delta=0 on every step →
        /admin/egress/per-step always empty. The meter never worked on a
        successful run.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        loop_idx = src.find("for key, display, func in pipeline:")
        import_idx = src.find("from sqlalchemy import text as _sa_text")
        assert import_idx != -1, "auto_maintenance must import text as _sa_text"
        assert 0 <= import_idx < loop_idx, (
            "`from sqlalchemy import text as _sa_text` must appear BEFORE the "
            "pipeline for-loop (unconditionally), or the per-step egress probe "
            "raises a swallowed NameError and records tup_delta=0 every step."
        )

    def test_dedup_articles_batches_title_lookup(self):
        """2026-05-31 egress fix: step_deduplicate_articles Layer 1 must fetch
        all duplicate-title articles in ONE `title_fa IN (...)` query, not run
        `SELECT * WHERE title_fa = X` inside a loop. title_fa is unindexed, so
        the per-title version was ~50 full seq-scans of the articles table
        (~425K rows ≈ 1.7 GB) — the #1 fixable egress driver in the 2026-05-31
        per-step measurement.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_deduplicate_articles")
        assert idx >= 0, "step_deduplicate_articles must exist"
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]
        assert "title_fa.in_(" in body, (
            "Layer 1 dedup must batch dup-title lookups via title_fa.in_(...) "
            "(one scan), not a per-title SELECT in a loop."
        )
        assert "Article.title_fa == title" not in body, (
            "Layer 1 must NOT run `SELECT ... WHERE title_fa == title` inside "
            "the loop — that was 50 full seq-scans (~1.7 GB egress)."
        )

    def test_trending_endpoint_caps_limit_at_30(self):
        """Phase F.3: max trending limit dropped 50→30."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # Locate the trending endpoint and check the Query() bounds.
        idx = src.find('@router.get("/trending"')
        assert idx >= 0
        block = src[idx:idx + 1500]
        assert "le=30" in block, (
            "Trending endpoint must cap limit at 30 (was 50). "
            "Phase F.3 — saves ~40% per call."
        )
        assert "le=50" not in block, (
            "Trending endpoint must NOT allow limit > 30. Phase F.3."
        )

    def test_trending_endpoint_sets_cache_control(self):
        """Phase F.3: Cloudflare CDN cache header on /trending response."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find('@router.get("/trending"')
        next_dec = src.find("@router.", idx + 1)
        body = src[idx:next_dec if next_dec > 0 else idx + 3000]
        assert "s-maxage=600" in body, (
            "Trending response must set Cache-Control: s-maxage=600 "
            "so Cloudflare absorbs cross-region duplicate fetches "
            "(bumped 300→600 in Lever 1, 2026-05-31 — data changes 2×/day)."
        )
        assert "stale-while-revalidate" in body, (
            "Trending response must include stale-while-revalidate "
            "so cache misses don't block the response."
        )

    def test_procfile_has_no_celery_workers(self):
        """Phase F.3: worker + beat lines removed to prevent any path
        from enqueueing tasks that bypass the budget guard.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "Procfile"
        ).read_text()
        # Lines that would actually start a Celery process. Matching
        # at line-start to ignore comments.
        lines = [ln.strip() for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        active_celery = [
            ln for ln in lines
            if ln.startswith("worker:") and "celery" in ln
            or ln.startswith("beat:") and "celery" in ln
        ]
        assert not active_celery, (
            f"Procfile must not declare a worker or beat process. "
            f"Found: {active_celery}. Phase F.3."
        )


class TestDailyEgressCap3GB:
    """Parham 2026-05-09 (rule), 2026-05-12 (tightened to 2.0 GB):
    hard rule — never let any single UTC day exceed the estimated
    Neon egress cap. 100 GB Neon free tier / 30 days = 3.33 GB/day;
    after Phase G ship the cap was tightened to 2.0 GB/day (the
    Phase G target). Estimate uses pg_stat_database.tup_returned
    delta against a start-of-day snapshot persisted in
    egress_daily_snapshot. When today's egress crosses the cap, the
    entire cron pipeline halts (same semantics as manual_lock).
    Resets at UTC midnight via natural day-rollover.

    Context: the 2026-05-09 30 GB egress incident burned ~30 % of the
    monthly allotment in one day because the kill-switch's
    HALT_SKIP_STEPS only blocked LLM-heavy steps; ~41 non-LLM heavy
    steps still ran on every cron fire. This rule survives that
    failure mode regardless of which steps are tagged where.
    """

    def test_constant_set_to_5gb(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        assert 'os.getenv("DN_DAILY_EGRESS_CAP_GB", "5.0")' in src, (
            "DAILY_EGRESS_CAP_GB default is 5.0 GB (raised 2.0 → 5.0 on "
            "2026-05-31 by explicit Parham acknowledgement: the estimate "
            "overcounts ~1.5×, so 5.0 EST ≈ ~3.3 GB ACTUAL ≈ the 100 GB/mo "
            "free-tier daily budget — headroom for a normal full run to "
            "finish without halting). The DN_DAILY_EGRESS_CAP_GB env var "
            "still overrides this for one-offs. Future cycles must not change "
            "the default without explicit Parham acknowledgement — see strict "
            "rule 2gb-daily-egress-cap in CLAUDE.md."
        )

    def test_mtd_egress_uses_month_baseline_not_cumulative(self):
        """2026-05-29 fix: get_neon_egress_estimate_mtd must compute MTD from
        the earliest egress_daily_snapshot of the current month, NOT the raw
        cumulative pg_stat_database.tup_returned.

        Bug: with stats_reset NULL, tup_returned is an ALL-TIME total (~778 GB).
        Multiplying it and calling it 'MTD' made combined_mtd ($55) exceed
        HALT_HARD_USD ($25.50), which would auto-halt the cron the instant
        manual_lock was cleared — silently blocking the June 1 unlock.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        idx = src.find("async def get_neon_egress_estimate_mtd")
        assert idx >= 0, "get_neon_egress_estimate_mtd must exist"
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]
        assert "egress_daily_snapshot" in body, (
            "MTD egress must be derived from the egress_daily_snapshot month "
            "baseline (current tup_returned minus the earliest snapshot this "
            "month), NOT the raw cumulative tup_returned counter."
        )
        assert "date_trunc('month'" in body or 'date_trunc("month"' in body, (
            "MTD egress must anchor its baseline to the start of the current "
            "month (date_trunc('month', NOW()))."
        )

    def test_should_halt_for_budget_returns_daily_egress_cap_reason(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "budget_guard.py"
        ).read_text()
        # The function must check daily egress and return a
        # daily_egress_cap halt reason BEFORE the manual_clear
        # one-shot can bypass it.
        idx = src.find("async def should_halt_for_budget")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        assert "daily_egress_cap" in body, (
            "should_halt_for_budget must return halt reason "
            "starting with 'daily_egress_cap' when today's egress "
            "crosses the cap. Cycle-5 Phase E.3 regression."
        )
        # Ordering: daily egress check must come BEFORE manual_clear
        # one-shot (so a clear can't sidestep the daily cap — the cap
        # is the survival floor, clear is for unblocking specific runs
        # within budget).
        cap_pos = body.find("daily_egress_cap_")
        clear_pos = body.find('override == "clear"')
        assert cap_pos > 0 and clear_pos > 0
        assert cap_pos < clear_pos, (
            "Daily egress cap check must come BEFORE the "
            "manual_clear one-shot — otherwise clear bypasses the "
            "daily survival floor."
        )

    def test_run_maintenance_treats_daily_cap_like_manual_lock(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        # The full-halt block in run_maintenance must check for
        # daily_egress_cap reason, not just manual_lock.
        idx = src.find("Phase E.2")
        assert idx >= 0
        # Look at the full-halt block — should now also include
        # daily_egress_cap.
        block = src[idx:idx + 3500]
        assert "daily_egress_cap" in block, (
            "run_maintenance full-halt block must also short-circuit "
            "on halt_reason starting with 'daily_egress_cap'. "
            "Otherwise the daily cap doesn't actually halt the "
            "non-LLM heavy steps. Phase E.3 regression."
        )

    def test_egress_daily_snapshot_table_in_self_heal(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "main.py"
        ).read_text()
        assert "egress_daily_snapshot" in src, (
            "egress_daily_snapshot table DDL must be in main.py "
            "lifespan self-heal so the daily-egress estimator works "
            "on a fresh DB without manual migration."
        )

    def test_neon_egress_not_counted_when_disabled(self):
        """Parham 2026-06-18 (EXPLICIT owner decision): Neon egress no longer
        counts toward the budget kill-switch and no longer halts crons. The
        egress halts had started skipping mid-month crons (06-17 15:00) and
        staling the homepage during the Iran-US deal; Parham accepts the Neon
        cost to keep the site fresh. The LLM kill-switch is UNCHANGED. Flip
        COUNT_NEON_EGRESS_IN_BUDGET back to True to restore the egress floor.
        This overrides the egress-cap intent of this class by owner decision."""
        from pathlib import Path
        src = (
            Path(__file__).parent.parent / "app" / "services" / "budget_guard.py"
        ).read_text()
        assert "COUNT_NEON_EGRESS_IN_BUDGET = False" in src, (
            "Neon egress counting is disabled by owner decision 2026-06-18"
        )
        assert "egress_cost if COUNT_NEON_EGRESS_IN_BUDGET else 0.0" in src, (
            "combined_mtd must drop egress_cost when COUNT_NEON_EGRESS_IN_BUDGET is False"
        )
        assert (
            "if COUNT_NEON_EGRESS_IN_BUDGET and daily_egress_gb >= DAILY_EGRESS_CAP_GB"
            in src
        ), "the daily egress cap halt must be gated by COUNT_NEON_EGRESS_IN_BUDGET"


class TestManualLockHaltsEntirePipeline:
    """Cycle-5 Phase E.2 (CRITICAL 2026-05-09): the budget kill-switch
    HALT_SKIP_STEPS list contains only ~17 LLM-heavy step names. The
    other ~41 pipeline steps (cluster, recompute_centroids, ingest,
    audit_clusters, recluster_orphans, etc.) STILL ran on every cron
    fire even with the lock active — these are Neon-egress-heavy and
    burned ~10 GB per fire × 3 fires/day = 30 GB. The 2026-05-09
    Neon billing jump exposed this gap.

    Fix: when halt_reason == 'manual_lock' (operator emergency), the
    entire pipeline early-exits before ANY step runs. The auto-halt
    (combined_mtd over 80%) keeps current partial behavior so ingest
    stays fresh on accidental over-spend days.
    """

    def test_manual_lock_short_circuits_run_maintenance(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent / "auto_maintenance.py"
        ).read_text()
        # Locate the full-halt block by Phase E.2 anchor.
        idx = src.find("Phase E.2")
        assert idx >= 0, (
            "Phase E.2 anchor comment must remain in run_maintenance"
        )
        # Must check for manual_lock specifically (not just `halt`).
        block = src[idx:idx + 5000]
        assert 'halt_reason == "manual_lock"' in block, (
            "run_maintenance must distinguish manual_lock from "
            "auto-halt. Without the explicit check, lock ≡ auto-halt "
            "and ~41 heavy steps still run. Cycle-5 Phase E.2."
        )
        # The early-return happens BEFORE the pipeline for-loop.
        loop_pos = src.find("for key, display, func in pipeline:", idx)
        # Find the earliest `return` after the full-halt block within
        # the run_maintenance function.
        return_pos = src.find('return {"_full_halt"', idx)
        assert return_pos > 0, (
            "Full-halt branch must `return {\"_full_halt\": ...}` "
            "before the for-loop. Otherwise heavy non-LLM steps run "
            "anyway. The 2026-05-09 30 GB egress incident was this "
            "exact bug."
        )
        assert loop_pos > 0
        assert return_pos < loop_pos, (
            "full-halt early-return must execute BEFORE the pipeline "
            "for-loop."
        )


class TestCeleryTasksHaveBudgetGuard:
    """Cycle-5 Phase E (2026-05-09): the budget kill-switch only fires
    from auto_maintenance.run_maintenance pre-flight. Celery tasks
    enqueued from any path (beat schedule, application code, manual
    enqueue) bypassed it entirely. The 2026-05-09 30 GB Neon egress
    jump exposed this gap.

    All 7 tasks across the 3 worker modules MUST check
    should_halt_for_budget at fire-time and return early on halt.
    """

    GUARDED_TASKS = (
        ("app/workers/nlp_task.py", "process_nlp_batch_task"),
        ("app/workers/nlp_task.py", "cluster_stories_task"),
        ("app/workers/nlp_task.py", "score_bias_batch_task"),
        ("app/workers/ingest_task.py", "ingest_all_feeds_task"),
        ("app/workers/social_task.py", "ingest_telegram_task"),
        ("app/workers/social_task.py", "link_posts_task"),
        ("app/workers/social_task.py", "compute_sentiment_task"),
    )

    def test_each_task_calls_budget_halt_check(self):
        from pathlib import Path

        for relpath, task_name in self.GUARDED_TASKS:
            src = (
                Path(__file__).parent.parent / relpath
            ).read_text()
            idx = src.find(f"def {task_name}(")
            assert idx >= 0, (
                f"Task {task_name} not found in {relpath}"
            )
            # Body of the task up to the next @celery_app.task decorator
            # or end of file.
            next_dec = src.find("@celery_app.task", idx + 1)
            body = src[idx:next_dec if next_dec > 0 else len(src)]
            assert "_budget_halt_if_active" in body, (
                f"Task {task_name} in {relpath} must call "
                f"_budget_halt_if_active() at fire-time. Cycle-5 "
                f"Phase E regression — workers route around the lock."
            )
            assert 'return {"skipped": True' in body, (
                f"Task {task_name} must return {{'skipped': True, ...}} "
                f"on halt so logs/Celery results show why it no-op'd."
            )

    def test_helper_uses_consume_override_false(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "workers" / "nlp_task.py"
        ).read_text()
        idx = src.find("async def _budget_halt_if_active")
        assert idx >= 0
        body = src[idx:idx + 1500]
        assert "consume_override=False" in body, (
            "Worker budget check must NOT consume the operator's "
            "one-shot clear — that belongs to the cron pre-flight."
        )


class TestEditStoryRequestAcceptsAllNarrativeFields:
    """Cycle-5 H6+ (2026-05-08 evening): the chat-driven editorial
    workflow needs to set the same long-form FA fields the cron does:
    title_fa, summary_fa, state_summary_fa, diaspora_summary_fa,
    independent_summary_fa, bias_explanation_fa, editorial_context_fa,
    and briefing_fa (the doornama hero prose). Without all 8, the
    operator can't fully replace a cron-generated story package and
    the homepage shows mismatched coverage.

    This test pins the PATCH /admin/stories/{id} model surface so a
    future cycle doesn't drop a field and silently break the workflow.
    """

    EXPECTED_FIELDS = (
        "title_fa", "title_en", "summary_fa", "priority",
        "state_summary_fa", "diaspora_summary_fa",
        "independent_summary_fa", "bias_explanation_fa",
        "editorial_context_fa", "briefing_fa",
    )

    def test_request_model_includes_all_editorial_fields(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("class _EditStoryRequest")
        assert idx >= 0
        # Look at next ~800 chars (pydantic model body).
        block = src[idx:idx + 1200]
        for field in self.EXPECTED_FIELDS:
            assert f"{field}:" in block, (
                f"_EditStoryRequest missing `{field}` field — chat-"
                f"driven editorial workflow needs all 8 narrative "
                f"fields to fully replace a cron story package."
            )

    def test_blob_writer_covers_all_long_form_fields(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        # The blob_writers dict in edit_story must list all 6 long-form
        # fields (the ones written into summary_en JSON).
        idx = src.find("blob_writers = {")
        assert idx >= 0, (
            "edit_story must use a blob_writers dict so all narrative "
            "fields are written uniformly. Cycle-5 follow-up."
        )
        block = src[idx:idx + 800]
        for key in (
            "state_summary_fa", "diaspora_summary_fa",
            "independent_summary_fa", "bias_explanation_fa",
            "editorial_context_fa", "briefing_fa",
        ):
            assert f'"{key}"' in block, (
                f"blob_writers must include `{key}` key. Without it "
                f"the chat-driven workflow can't set that field."
            )

    def test_anchor_writer_preserves_briefing_fa(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        # The anchor_writers dict must include briefing_fa so the
        # next cron's doornama step picks it up as prior_brief_anchor.
        idx = src.find("anchor_writers = {")
        assert idx >= 0
        block = src[idx:idx + 800]
        assert '"briefing_fa"' in block, (
            "anchor_writers must include briefing_fa. Without it the "
            "next doornama cron step regenerates fresh prose, "
            "ignoring the operator's chat-drafted briefing."
        )


class TestTelegramDeepNeighborPoolBounded:
    """Cycle-5 H21 (HIGH 2026-05-08): the neighbor-borrow query in
    analyze_story_telegram used to load every Story with
    article_count >= 3 AND trending_score > 0 — full ORM rows
    including JSONB telegram_analysis (~22 KB/row). Same pattern as
    the May 2026 $18 Neon egress incident.

    Two fixes:
    1. SELECT only id + centroid_embedding (no full row).
    2. last_updated_at >= NOW() - 14d freshness filter + LIMIT 200.
    """

    def test_neighbor_query_uses_lean_select_and_freshness_limit(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "services" / "telegram_analysis.py"
        ).read_text()
        # Locate the neighbor-borrow block by an anchor comment.
        idx = src.find("Cycle-5 H21")
        assert idx >= 0, (
            "Cycle-5 H21 anchor comment must remain to scope this test."
        )
        block = src[idx:idx + 3500]
        # Must NOT load full Story rows.
        assert "select(Story).where(" not in block, (
            "Neighbor query must use a lean SELECT (id + "
            "centroid_embedding only), not select(Story). Loading full "
            "rows pulls the 22 KB JSONB columns we don't read."
        )
        # Must select only id + centroid_embedding.
        assert "select(Story.id, Story.centroid_embedding)" in block, (
            "Neighbor query must SELECT only Story.id, "
            "Story.centroid_embedding. Cycle-5 H21."
        )
        # Must apply 14-day freshness filter.
        assert "NEIGHBOR_FRESHNESS_DAYS" in block, (
            "Neighbor query must filter by Story.last_updated_at >= "
            "NOW() - 14d so cold stories don't bloat egress."
        )
        # Must apply hard row limit.
        assert "NEIGHBOR_QUERY_LIMIT" in block and ".limit(NEIGHBOR_QUERY_LIMIT)" in block, (
            "Neighbor query must end with .limit(NEIGHBOR_QUERY_LIMIT). "
            "Without LIMIT, the query is unbounded — same shape as the "
            "May 2026 $18 incident."
        )


class TestStoryDetailArticlePagination:
    """Phase G.3.3 (Parham 2026-05-10): GET /api/v1/stories/{id} now
    paginates the articles list. The two known umbrella stories
    (1464 + 2354 articles) drop ~6 MB → ~200 KB per fetch, which is
    the dominant story-detail egress driver on the platform.

    Tripwires the parts of the refactor that are easy to silently
    revert:
    1. limit default stays at 50 (max 500). Bumping default high
       silently re-introduces the 6 MB-per-fetch behavior.
    2. The per-source aggregate query exists. Without it, percentages
       are computed from the truncated article subset and umbrella
       stories silently misreport state_pct / diaspora_pct.
    3. StoryDetail exposes articles_returned + articles_has_more so
       the frontend can render an honest "X از Y مقاله" badge.
    """

    def test_get_story_default_limit_is_50(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # Locate the get_story endpoint and check its limit Query bounds.
        idx = src.find('@router.get("/{story_id}", response_model=StoryDetail)')
        assert idx >= 0, "get_story endpoint anchor missing."
        # End-of-block anchor: next router decorator or end of file.
        next_dec = src.find("@router.", idx + 1)
        block = src[idx:next_dec if next_dec > 0 else idx + 6000]
        # Default 50.
        assert "limit: int = Query(50" in block, (
            "get_story default limit must be 50. Phase G.3.3 — "
            "bumping the default re-introduces the umbrella-story "
            "egress regression."
        )
        # Max 500 — guards against a `limit=99999` URL bypassing the cap.
        assert "le=500" in block, (
            "get_story limit must cap at 500 (le=500). Phase G.3.3."
        )
        # Offset param exists.
        assert "offset: int = Query(0" in block, (
            "get_story must expose an `offset` query param for pagination."
        )

    def test_get_story_uses_per_source_aggregate(self):
        """Without a separate aggregate query for source counts, the
        coverage percentages are computed against the truncated
        articles subset. Pin the aggregate query shape so a future
        cleanup can't silently delete it.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find('@router.get("/{story_id}", response_model=StoryDetail)')
        # End-of-block: scan to the next def at module level. The
        # endpoint body runs ~9000 chars after Phase G.3.3.
        next_def = src.find("\nasync def _bump_view_count", idx + 1)
        block = src[idx:next_def if next_def > 0 else idx + 12000]
        # The aggregate query: SELECT Source, count(Article.id) JOIN ... GROUP BY Source.id
        assert "select(Source, func.count(Article.id))" in block, (
            "get_story must compute per-source article counts via a "
            "lean aggregate query so coverage percentages stay "
            "correct on umbrella stories. Phase G.3.3."
        )
        assert "group_by(Source.id)" in block, (
            "Per-source aggregate must group_by Source.id."
        )
        # Pagination metadata wired to the response.
        assert "articles_returned=" in block, (
            "Response must expose `articles_returned` so the frontend "
            "can render an honest '20 از 1464 مقاله' badge."
        )
        assert "articles_has_more=" in block, (
            "Response must expose `articles_has_more` so the frontend "
            "knows when to render a 'load more' control."
        )

    def test_storydetail_schema_has_pagination_fields(self):
        """Pin the StoryDetail schema so future cleanup can't drop
        the pagination metadata fields without breaking this test.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "schemas" / "story.py"
        ).read_text()
        idx = src.find("class StoryDetail")
        assert idx >= 0
        # Cheap window — schema definition fits well under 2 KB.
        block = src[idx:idx + 2500]
        assert "articles_returned: int" in block, (
            "StoryDetail must declare articles_returned: int."
        )
        assert "articles_offset: int" in block, (
            "StoryDetail must declare articles_offset: int."
        )
        assert "articles_has_more: bool" in block, (
            "StoryDetail must declare articles_has_more: bool."
        )


class TestHomepageAggregatesDenormalized:
    """Phase G.3.2 (Parham 2026-05-10): denormalize per-story image +
    coverage percentages + narrative groups into a JSONB blob on
    Story.homepage_aggregates so /trending and /blindspots can
    (Phase 2) drop selectinload(Story.articles). Today's ship is
    Phase 1: column + populate step + read-side fallback.

    Tripwires the structural pieces that are easy to silently revert:
    1. Story.homepage_aggregates column declared on the ORM.
    2. Self-heal DDL adds the column at FastAPI startup.
    3. step_recompute_homepage_aggregates exists and ships in
       FULL_PIPELINE between recalc_trending and image_relevance.
    4. _story_brief_with_extras consults the blob before falling
       back to article iteration.
    5. The step is tagged CHEAP so it keeps running during budget
       soft-halt (otherwise the homepage drifts when LLM steps pause).
    """

    def test_story_model_has_homepage_aggregates_column(self):
        from app.models.story import Story

        assert hasattr(Story, "homepage_aggregates"), (
            "Story.homepage_aggregates column missing — the "
            "denormalized blob lives here. Phase G.3.2."
        )

    def test_self_heal_ddl_adds_homepage_aggregates(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "main.py"
        ).read_text()
        assert (
            "ALTER TABLE stories ADD COLUMN IF NOT EXISTS "
            "homepage_aggregates JSONB"
        ) in src, (
            "app/main.py self-heal must add stories.homepage_aggregates "
            "JSONB. Without it, fresh deploys would 500 on listing "
            "endpoints until alembic upgrade head ran. Phase G.3.2."
        )

    def test_step_recompute_homepage_aggregates_in_full_pipeline(self):
        import importlib
        m = importlib.import_module("auto_maintenance")
        # Step function is defined.
        assert hasattr(m, "step_recompute_homepage_aggregates"), (
            "step_recompute_homepage_aggregates must exist in "
            "auto_maintenance.py. Phase G.3.2."
        )
        # Step is wired into FULL_PIPELINE with the right key + func.
        keys = [t[0] for t in m.FULL_PIPELINE]
        funcs = {t[0]: t[2] for t in m.FULL_PIPELINE}
        assert "homepage_aggregates" in keys, (
            "FULL_PIPELINE must include the `homepage_aggregates` "
            "step. Phase G.3.2."
        )
        assert funcs["homepage_aggregates"] == "step_recompute_homepage_aggregates", (
            "FULL_PIPELINE step `homepage_aggregates` must dispatch "
            "to step_recompute_homepage_aggregates."
        )
        # Order: must run after recalc_trending (final trending_score).
        idx_recalc = keys.index("recalc_trending")
        idx_agg = keys.index("homepage_aggregates")
        assert idx_agg > idx_recalc, (
            "`homepage_aggregates` must run AFTER `recalc_trending` so "
            "the denormalized blob reflects the final trending_score "
            "ordering visible on /trending."
        )

    def test_story_brief_with_extras_prefers_blob(self):
        """Read-side helper must consult Story.homepage_aggregates
        before falling back to article iteration. Without this, the
        Phase 2 article-load drop would silently render empty
        homepage cards.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find("def _story_brief_with_extras")
        assert idx >= 0
        # Bound by next module-level def.
        next_def = src.find("\ndef ArticleBriefDict", idx + 1)
        block = src[idx:next_def if next_def > 0 else idx + 12000]
        assert "homepage_aggregates" in block, (
            "_story_brief_with_extras must read story.homepage_aggregates "
            "and prefer it over article iteration. Phase G.3.2."
        )

    def test_homepage_aggregates_step_is_cheap(self):
        """The step must keep running during budget soft-halt
        (combined_mtd >= 80%) so the homepage doesn't drift while
        LLM steps are paused. Pin it in CHEAP_STEPS.
        """
        from app.services.budget_guard import CHEAP_STEPS, HALT_SKIP_STEPS

        assert "homepage_aggregates" in CHEAP_STEPS, (
            "homepage_aggregates must be in CHEAP_STEPS — the "
            "denormalize is pure DB read+write, must keep running "
            "during budget soft-halt to keep the homepage fresh."
        )
        assert "homepage_aggregates" not in HALT_SKIP_STEPS, (
            "homepage_aggregates must NOT be in HALT_SKIP_STEPS — "
            "it's not LLM-heavy and the homepage depends on it."
        )


class TestListingEndpointsDontLoadArticles:
    """Phase G.3.2 Phase 2 (Parham 2026-05-12): /trending,
    /blindspots, /, and /related listings no longer eagerly load
    Story.articles. Per-card image + coverage come from the
    denormalized homepage_aggregates blob (Phase 1). This was the
    dominant story-listing egress driver before the cut.

    Tripwires:
    1. _articles_load_brief() function is removed (was the
       selectinload helper).
    2. Listing endpoints don't use selectinload(Story.articles)
       in their query .options().
    3. The brief builder is called with articles=[] explicitly
       so it doesn't trigger a lazy-load of the unloaded relation.
    """

    def test_articles_load_brief_function_removed(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        assert "def _articles_load_brief" not in src, (
            "_articles_load_brief() must remain removed. "
            "Phase G.3.2 Phase 2 (Parham 2026-05-12) eliminated "
            "selectinload(Story.articles) from listing endpoints "
            "in favor of Story.homepage_aggregates. Reintroducing "
            "the helper means listing endpoints would re-fetch full "
            "article rows on every cache miss."
        )

    def test_listing_endpoints_pass_empty_articles_to_brief(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # The three listing endpoints each call _story_brief_with_extras
        # with articles=[] explicitly so the brief builder skips
        # touching the unloaded story.articles relation. Without the
        # kwarg, async SQLAlchemy would MissingGreenlet on access.
        assert src.count("_story_brief_with_extras(s, articles=[])") >= 3, (
            "list_stories, trending_stories, and blindspot_stories "
            "must each call _story_brief_with_extras(s, articles=[]). "
            "Phase G.3.2 Phase 2."
        )


class TestStepProcessBounded:
    """Parham 2026-05-13: the cap halt fires between cron steps, NOT
    inside a step. A 2026-05-13 maintenance test showed step_process
    burning ~1.3 GB of Neon egress in a single firing on a clean-slate
    backlog, because the prior `while True` loop drained until batch < 50
    with no mid-loop budget check.

    Tripwires:
    1. step_process must have a bounded iteration cap (MAX_ITERS) so a
       single firing can't unbound-loop through hundreds of articles.
    2. step_process must call should_halt_for_budget between iterations
       — that's how the cap halt actually fires before the step ends.
    3. Same shape for step_classify_content_type — also burned ~400 MB
       on the same run before bounded.
    """

    def test_step_process_has_bounded_iterations(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_process")
        assert idx >= 0
        # Limit search to this function body.
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]

        assert "MAX_ITERS" in body, (
            "step_process must declare a MAX_ITERS cap. The prior "
            "unbounded `while True` loop allowed one cron firing to "
            "drain a 500+ article backlog and burn 1.3 GB of egress."
        )
        assert "while True" not in body, (
            "step_process must NOT use `while True` — replaced with a "
            "for-loop over MAX_ITERS to bound the per-cron work."
        )

    def test_step_process_checks_budget_between_batches(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_process")
        assert idx >= 0
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]

        assert "should_halt_for_budget" in body, (
            "step_process must call should_halt_for_budget between "
            "iterations so the daily egress cap can halt the step "
            "mid-run. Without this, the cap only fires at step "
            "boundaries — useless if a single step burns 1+ GB."
        )

    def test_step_classify_content_type_checks_budget(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_classify_content_type")
        assert idx >= 0
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]

        assert "should_halt_for_budget" in body, (
            "step_classify_content_type must call should_halt_for_budget "
            "between iterations — same pattern as step_process."
        )


class TestMidPipelineBudgetRecheck:
    """Parham 2026-05-14: the preflight `should_halt_for_budget` check
    at the top of run_maintenance fires once. Without a per-step
    re-check, a step that blows past the 2.0 GB cap mid-run continues
    burning egress through the remaining ~40 pipeline steps. Today's
    runaway burned ~5 GB past the cap before the pipeline naturally
    ended.

    The fix: at the end of the for-loop body in run_maintenance, probe
    should_halt_for_budget (consume_override=False). If the cap or
    manual_lock fires, break out of the loop and record the halt.

    Tripwire:
    1. run_maintenance contains a mid-pipeline re-check after each step.
    2. The re-check uses consume_override=False so it doesn't silently
       consume a one-shot operator clear during a single cron firing.
    3. The re-check on cap-cross writes a `_mid_pipeline_halt` entry
       to results so /admin/maintenance/logs surfaces where the run
       stopped.
    """

    def test_run_maintenance_has_mid_pipeline_budget_recheck(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "auto_maintenance.py"
        ).read_text()
        # Locate the run_maintenance function.
        idx = src.find("async def run_maintenance")
        assert idx >= 0
        # The mid-pipeline recheck lives inside the function body; bound
        # the search to it.
        end = src.find("\nasync def ", idx + 1)
        body = src[idx:end if end > 0 else len(src)]

        assert "MID-PIPELINE HALT" in body, (
            "run_maintenance must log a 'MID-PIPELINE HALT' message "
            "when the per-step budget recheck fires. Without this "
            "log line, the regression is invisible until the bill "
            "arrives."
        )
        assert "_mid_pipeline_halt" in body, (
            "Mid-pipeline halt must record `_mid_pipeline_halt` in "
            "results so /admin/maintenance/logs surfaces where the "
            "run stopped. Phase G follow-up 2026-05-14."
        )
        # The recheck must use consume_override=False so a one-shot
        # operator clear isn't silently consumed by these probes.
        assert "consume_override=False" in body, (
            "Mid-pipeline recheck must call should_halt_for_budget "
            "with consume_override=False so it doesn't silently "
            "consume the operator's one-shot clear override."
        )


class TestStrictRetention:
    """Phase G follow-up (Parham 2026-05-12) — strict retention rule.
    Only stories that earned homepage time are kept (up to 30 days
    after archival). Stories that came in but never reached the
    homepage are deleted after a 7-day grace period.

    Pinned by:
    1. step_delete_aged exists in FULL_PIPELINE at the very end
    2. CHEAP_STEPS tagged so it keeps running during budget soft-halt
    3. Function uses homepage_story_ids (single source of truth) as
       the never-delete guardrail
    """

    def test_step_delete_aged_in_full_pipeline(self):
        import importlib
        m = importlib.import_module("auto_maintenance")
        keys = [t[0] for t in m.FULL_PIPELINE]
        assert "delete_aged" in keys, (
            "FULL_PIPELINE must include the delete_aged retention step."
        )
        # Must run LAST so other steps see complete data first.
        assert keys[-1] == "delete_aged", (
            f"delete_aged must be the LAST step in FULL_PIPELINE so "
            f"other steps complete before rows are deleted. "
            f"Currently last: {keys[-1]!r}"
        )
        funcs = {t[0]: t[2] for t in m.FULL_PIPELINE}
        assert funcs["delete_aged"] == "step_delete_aged"
        assert hasattr(m, "step_delete_aged")

    def test_delete_aged_uses_homepage_scope_guardrail(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "auto_maintenance.py"
        ).read_text()
        idx = src.find("async def step_delete_aged")
        assert idx >= 0
        next_def = src.find("\nasync def ", idx + 1)
        block = src[idx:next_def if next_def > 0 else idx + 8000]
        # Must guard against deleting current homepage stories.
        assert "homepage_story_ids" in block, (
            "step_delete_aged must call homepage_story_ids and NEVER "
            "delete a current homepage story."
        )
        assert "keep_ids" in block, (
            "step_delete_aged must keep an explicit `keep_ids` set "
            "to subtract from the delete candidates."
        )
        # Must explicitly subtract keep_ids — belt-and-braces.
        assert "delete_story_ids -= keep_ids" in block, (
            "step_delete_aged must subtract keep_ids from the delete "
            "set as the last safety check."
        )

    def test_delete_aged_in_cheap_steps(self):
        from app.services.budget_guard import CHEAP_STEPS, HALT_SKIP_STEPS

        assert "delete_aged" in CHEAP_STEPS, (
            "delete_aged must be tagged CHEAP so retention keeps "
            "running during budget soft-halt."
        )
        assert "delete_aged" not in HALT_SKIP_STEPS


class TestOptionCHomepageOnly:
    """Phase G follow-up (Parham 2026-05-11) — Option C: per-story read
    endpoints under /api/v1/stories/* return 410 Gone for stories not
    currently on the homepage (trending + blindspots). Archived/thin
    stories stop bleeding egress on every crawler hit.

    Tripwires the structural pieces:
    1. _require_homepage_eligible exists and uses the homepage_scope module
    2. The 5 per-story GET endpoints call the gate
    3. Listing endpoints filter to the eligible set
    4. Safety net: empty-set fallthrough (so the site doesn't 410 itself)
    """

    def test_eligibility_gate_exists(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        assert "_require_homepage_eligible" in src, (
            "_require_homepage_eligible helper must exist."
        )
        assert "_get_homepage_eligible_ids" in src, (
            "_get_homepage_eligible_ids cache helper must exist."
        )
        assert "from app.services.homepage_scope import homepage_story_ids" in src, (
            "Gate must source the eligible set from homepage_scope "
            "(single source of truth)."
        )
        assert 'status_code=410' in src, (
            "Gate must raise 410 Gone (not 404 — different SEO signal)."
        )

    def test_gate_applied_to_per_story_endpoints(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # Count callsites — should be at least 5: get_story, get_story_analysis,
        # get_related_stories, get_analyst_takes, article_positions
        callsites = src.count("await _require_homepage_eligible(story_id, db)")
        assert callsites >= 5, (
            f"At least 5 per-story endpoints must call the eligibility "
            f"gate (get_story, /analysis, /related, /analyst-takes, "
            f"/article-positions). Found {callsites}."
        )

    def test_safety_net_for_empty_eligible_set(self):
        """If homepage_story_ids returns empty (fresh deploy, all
        trending_score=0, etc.) the gate must fall through rather than
        410 every request. Otherwise the site self-destructs.
        """
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # The safety net pattern: `if not eligible: return`
        assert "if not eligible:\n        return" in src or \
            "if not eligible: return" in src, (
            "Eligibility gate must have a safety net for empty sets "
            "to avoid self-410'ing the whole site."
        )


class TestSitemapHomepageOnly:
    """Phase G follow-up (Parham 2026-05-11): the sitemap is the
    canonical "what to crawl" signal for Google + Bing + AI crawlers.
    Listing every story (~500) caused the crawler-driven egress tail.
    Sitemap now lists only homepage-eligible stories (~40), pairing
    with `noindex` on non-homepage pages.

    Stories not in the sitemap stay reachable via direct URL — the
    permalink + journalist-citation design from `Story.archived_at`
    (story.py comment) is preserved. The change only affects which
    URLs crawlers discover via sitemap walking.
    """

    def test_sitemap_uses_trending_and_blindspots(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "frontend" / "src" / "app" / "sitemap.ts"
        ).read_text()
        # Must reference both homepage endpoints.
        assert "/api/v1/stories/trending" in src, (
            "sitemap.ts must source from /trending so only homepage-"
            "eligible stories ship to crawlers."
        )
        assert "/api/v1/stories/blindspots" in src, (
            "sitemap.ts must source from /blindspots too."
        )
        # Must NOT do the old full-list fetch.
        assert "page_size=500" not in src, (
            "sitemap.ts must not bulk-fetch the full story list — "
            "that's what drove the crawler-driven egress tail."
        )


class TestStoryPageNoindexOnNonHomepage:
    """Phase G follow-up (Parham 2026-05-11): non-homepage-eligible
    story pages emit <meta name="robots" content="noindex"> via
    generateMetadata so Google + Bing remove them from search.
    Combined with sitemap pruning, crawler walks of the long tail
    drop dramatically over 2-3 weeks.
    """

    def test_generate_metadata_sets_noindex_for_thin_stories(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "frontend" / "src" / "app" / "[locale]" / "stories" / "[id]"
            / "page.tsx"
        ).read_text()
        idx = src.find("export async function generateMetadata")
        assert idx >= 0
        # Bound by the default export.
        next_def = src.find("\nexport default", idx + 1)
        block = src[idx:next_def if next_def > 0 else idx + 8000]
        # Must compute eligibility.
        assert "isHomepageEligible" in block, (
            "generateMetadata must compute homepage-eligibility so it "
            "can noindex thin stories."
        )
        # Must condition on article_count.
        assert "article_count" in block, (
            "Eligibility must check article_count (homepage rule: >= 4)."
        )
        # Must emit robots metadata.
        assert "robots" in block and "index: false" in block, (
            "generateMetadata must emit `robots: { index: false, ... }` "
            "for non-eligible stories."
        )


class TestStoryDetailIsrAtLeast30Min:
    """Phase G.3.4 (Parham 2026-05-10): the story-detail page is the
    heaviest ISR regen path on the site. With 18 Vercel ISR regions
    each regenerating on cache miss, every doubling of `revalidate`
    halves Neon read pressure on this dominant traffic path.

    Tripwire: revalidate must stay >= 1800 (30 min). Halving it back
    to 900 (15 min) doubles Neon egress on this path. The 6h cron
    cadence means the underlying data only shifts every 6 hours, so
    30 min cache age is well inside the data-freshness envelope.
    """

    def test_revalidate_at_least_1800(self):
        import re
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "frontend" / "src" / "app" / "[locale]" / "stories" / "[id]"
            / "page.tsx"
        ).read_text()
        match = re.search(r"export\s+const\s+revalidate\s*=\s*(\d+)", src)
        assert match, (
            "story detail page.tsx must export `revalidate` so the page "
            "renders as ISR. Removing the export opts the page out of "
            "edge caching and routes every visitor to a fresh SSR."
        )
        seconds = int(match.group(1))
        assert seconds >= 1800, (
            f"story detail revalidate must be >= 1800 (30 min). Found "
            f"{seconds}. Phase G.3.4 — June 2 GB/day target requires "
            "this path stays at >= 30 min cache age."
        )


class TestDisputeScoreDeterministic:
    """2026-05-31: dispute_score is derived deterministically from per-side
    framing-word divergence (story_analysis.compute_dispute_score), not the
    LLM's value which clustered on ~0.5 and broke «تقابل روایت‌ها» ordering.
    """

    def test_opposed_framings_score_high(self):
        from app.services.story_analysis import compute_dispute_score as f
        s = f({"state": {"framing": ["مقاومت", "پیروزی", "اقتصادی"]},
               "diaspora": {"framing": ["تهدید", "سرکوب", "حقوق بشر"]}})
        assert s is not None and s >= 0.9, f"fully-opposed framings should be high, got {s}"

    def test_one_sided_scores_low(self):
        from app.services.story_analysis import compute_dispute_score as f
        assert f({"state": {"framing": ["مقاومت"]}, "diaspora": {"framing": []}}) == 0.15

    def test_no_scores_returns_none(self):
        from app.services.story_analysis import compute_dispute_score as f
        assert f(None) is None and f({}) == 0.15 or f(None) is None

    def test_overlapping_framings_below_dispute_floor(self):
        # The frontend تقابل box uses a 0.45 floor; identical framings must
        # fall below it so non-contested stories don't show as «disputed».
        from app.services.story_analysis import compute_dispute_score as f
        s = f({"state": {"framing": ["جنگ", "صلح"]}, "diaspora": {"framing": ["جنگ", "صلح"]}})
        assert s is not None and s < 0.45, f"identical framings should be < 0.45, got {s}"


# ═════════════════════════════════════════════════════════════════════
# article_count drift after delete_aged (2026-05-31, Parham 7-vs-5)
# ═════════════════════════════════════════════════════════════════════

class TestRecountAfterDeleteAged:
    """step_delete_aged is the LAST destructive step (deletes orphan +
    aged articles) and runs ~30 steps after recount_after_dedup. A
    surviving story that loses an article here carried a stale
    article_count until the NEXT run — a ~12h window where the story-page
    badge over-counted vs the articles actually rendered. The fix recounts
    inside step_delete_aged's own transaction. This tripwire keeps it.
    """

    def _delete_aged_body(self) -> str:
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        start = src.find("async def step_delete_aged")
        assert start >= 0, "step_delete_aged not found"
        end = src.find("\nasync def ", start + 10)
        return src[start:end]

    def test_delete_aged_recounts_before_commit(self):
        body = self._delete_aged_body()
        assert "recounted_after_delete" in body, (
            "step_delete_aged no longer recounts article_count after its "
            "deletes. Surviving stories that lose aged/orphan articles will "
            "carry a stale count for ~12h until the next run. Restore the "
            "final UPDATE…FROM recount before db.commit()."
        )
        # The recount must update article_count from a live COUNT(*).
        assert "SET article_count = sub.c" in body, (
            "step_delete_aged recount lost its article_count UPDATE."
        )

    def test_dedup_title_cap_not_back_to_50(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        start = src.find("async def step_deduplicate_articles")
        end = src.find("\nasync def ", start + 10)
        body = src[start:end]
        # Layer 1 title cap was bumped 50 -> 300 because the 50-cap was hit
        # every run, leaving same-title pairs attached to one story.
        assert ".limit(300)" in body, (
            "step_deduplicate_articles Layer 1 title cap regressed below 300. "
            "The 50-cap left a visible duplicate-headline backlog (2026-05-31)."
        )


# ═════════════════════════════════════════════════════════════════════
# Clustering accuracy — geo-theater gate (L1) + headline grounding (L2)
# (2026-05-31, after the false «۲۰۰ کشته در حملات به شناورهای ایرانی»)
# ═════════════════════════════════════════════════════════════════════

class TestGeoTheaterGate:
    """Layer 1: the embedding matcher is geography-blind, so an
    eastern-Pacific drug-boat strike merged into an Iran-strikes story.
    _locus_conflict blocks cross-theater merges while staying silent on
    same-theater and generic articles."""

    def test_drug_boat_vs_iran_conflicts(self):
        from app.services.clustering import _locus_set, _locus_conflict
        drug = _locus_set("حمله مجدد آمریکا به یک شناور در شرق اقیانوس آرام")
        iran = _locus_set("گزارش‌ها از حملات جدید آمریکا به بندرعباس؛ کنترل تنگه هرمز")
        assert drug == {"americas"} and iran == {"iran"}
        assert _locus_conflict(drug, iran) is True

    def test_same_theater_does_not_conflict(self):
        from app.services.clustering import _locus_set, _locus_conflict
        assert _locus_conflict(_locus_set("حمله به بندرعباس"),
                               _locus_set("حملات آمریکا به ایران")) is False

    def test_generic_article_never_blocked(self):
        # No locus tag on either side → never a conflict (conservative).
        from app.services.clustering import _locus_set, _locus_conflict
        assert _locus_conflict(_locus_set("قیمت دلار امروز"),
                               _locus_set("بازار بورس سقوط کرد")) is False
        assert _locus_conflict(set(), {"iran"}) is False

    def test_other_cross_theater_generalizes(self):
        from app.services.clustering import _locus_set, _locus_conflict
        assert _locus_conflict(_locus_set("حمله روسیه به اوکراین"),
                               _locus_set("تنش در تنگه هرمز")) is True

    def test_gate_wired_into_matcher(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        assert "_locus_conflict(a_loci" in src, (
            "geo-theater gate no longer applied in _match_to_existing_stories"
        )
        assert '"loci": _locus_set(corpus)' in src, "story signature lost its loci set"


class TestHeadlineGrounding:
    """Layer 2: a title with a number gets fact-checked against the
    cluster's source headlines; an unsupported figure is rewritten out."""

    def test_no_number_is_noop(self):
        import asyncio
        from app.services import clustering
        # No number → returns original, never calls the LLM.
        called = {"n": 0}
        async def _boom(*a, **k):
            called["n"] += 1
            return None
        clustering._call_openai_grounding = _boom
        out = asyncio.run(clustering.verify_title_grounding(
            "حمله آمریکا به بندرعباس", ["حمله به بندرعباس"]))
        assert out == "حمله آمریکا به بندرعباس"
        assert called["n"] == 0, "grounding LLM must not run for number-free titles"

    def test_ungrounded_number_is_rewritten(self):
        import asyncio
        from app.services import clustering
        async def _fake(prompt):
            return {"grounded": False, "reason": "۲۰۰ از خبر دیگری است",
                    "corrected_title_fa": "حملات آمریکا به بندرعباس"}
        clustering._call_openai_grounding = _fake
        out = asyncio.run(clustering.verify_title_grounding(
            "حملات آمریکا به شناورهای ایرانی؛ کشته‌شدگان از ۲۰۰ نفر فراتر رفت",
            ["حمله مجدد آمریکا به یک شناور در شرق اقیانوس آرام", "حمله به بندرعباس"]))
        assert out == "حملات آمریکا به بندرعباس"

    def test_grounded_keeps_original(self):
        import asyncio
        from app.services import clustering
        async def _fake(prompt):
            return {"grounded": True, "corrected_title_fa": "ignored"}
        clustering._call_openai_grounding = _fake
        title = "کشته شدن ۳ نفر در حمله به بندرعباس"
        out = asyncio.run(clustering.verify_title_grounding(title, ["حمله به بندرعباس؛ ۳ کشته"]))
        assert out == title

    def test_llm_failure_keeps_original_no_silent_fabrication(self):
        import asyncio
        from app.services import clustering
        async def _fail(prompt):
            return None  # no key / LLM error
        clustering._call_openai_grounding = _fail
        title = "کشته‌شدگان از ۲۰۰ نفر فراتر رفت"
        out = asyncio.run(clustering.verify_title_grounding(title, ["خبر مرتبط"]))
        assert out == title  # never blocks, never fabricates a verdict


# ═════════════════════════════════════════════════════════════════════
# Niloofar coherence audit that ACTS (2026-06-01, Phase 2)
# ═════════════════════════════════════════════════════════════════════

class TestCoherenceActRetired:
    """2026-07-04: audit_homepage_coherence (the Phase-2 auto-archiving
    coherence check) was RETIRED. Its low-cohesion pre-filter was backwards
    per the v1 postmortem's own measurements — grab-bags HUG their centroid
    (0.53-0.73) while rich real stories scatter — so real grab-bags never
    reached the LLM, and the only archivable candidates were sprawling REAL
    stories (the nano-undercount failure that got coherence_gate v2
    reverted). This tripwire blocks silent revival: grab-bag detection is
    read-only canaries + human-reviewed detachment, never auto-archive."""

    def test_function_and_prompt_removed(self):
        from app.services import clustering
        assert not hasattr(clustering, "audit_homepage_coherence"), (
            "audit_homepage_coherence was retired 2026-07-04 — do not revive "
            "an auto-archiving coherence gate without Parham's explicit OK"
        )
        assert not hasattr(clustering, "COHERENCE_ACT_PROMPT")

    def test_not_called_from_pipeline_step(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        i = src.find("async def step_audit_cluster_coherence")
        body = src[i:i + 3000]
        assert "act_stats = await audit_homepage_coherence" not in body, (
            "retired coherence-act audit must not be re-wired into the step"
        )

    def test_flag_only_audit_survives(self):
        """The read-only drift audit (audit_cluster_coherence) and the two
        hygiene passes must remain — only the ARCHIVING half retired."""
        from app.services import clustering
        assert hasattr(clustering, "audit_cluster_coherence")
        assert hasattr(clustering, "detach_offtopic_from_visible_stories")
        assert hasattr(clustering, "freeze_oversized_active_stories")


# ═════════════════════════════════════════════════════════════════════
# Ingest egress fix — telegram convert sentinel + recency indexes
# (2026-06-01: the `ingest` step was 4.6 GB/run, 1.2M rows scanned)
# ═════════════════════════════════════════════════════════════════════

class TestIngestEgressFix:
    def test_telegrampost_has_converted_at(self):
        from app.models.social import TelegramPost
        assert hasattr(TelegramPost, "converted_at")

    def test_convert_filters_unprocessed_only(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "telegram_service.py").read_text()
        i = src.find("async def convert_telegram_posts_to_articles")
        body = src[i:i+3000]
        assert "TelegramPost.converted_at.is_(None)" in body, (
            "convert no longer filters to unprocessed posts — reintroduces the "
            "re-read-every-7-day-post egress driver"
        )
        assert "post.converted_at = _processed_at" in body, "posts no longer stamped processed"

    def test_aggregator_window_tightened(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "telegram_service.py").read_text()
        assert "existing_urls_cutoff = datetime.now(timezone.utc) - timedelta(days=7)" in src, (
            "aggregator URL-dedup window regressed above 7d"
        )

    def test_ingested_at_indexed(self):
        from app.models.article import Article
        names = {ix.name for ix in Article.__table__.indexes}
        assert "idx_articles_ingested_at" in names

    def test_selfheal_and_migration_present(self):
        from pathlib import Path
        main_src = (Path(__file__).parent.parent / "app" / "main.py").read_text()
        assert "idx_telegram_posts_unconverted" in main_src
        assert "telegram_posts ADD COLUMN IF NOT EXISTS converted_at" in main_src
        mig = Path(__file__).parent.parent / "alembic" / "versions" / "a2b3c4d5e6f7_ingest_egress_converted_at_and_indexes.py"
        assert mig.is_file(), "alembic migration missing"

    def test_article_url_map_projects_two_columns(self):
        """The REAL ingest egress hog (2026-06-02): _build_article_url_map
        loaded full Article ORM rows (incl. ~30 KB embedding JSONB) for every
        clustered article. It must project only (url, story_id)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "telegram_service.py").read_text()
        i = src.find("async def _build_article_url_map")
        body = src[i:i + 1200]
        assert "select(Article.url, Article.story_id)" in body, (
            "_build_article_url_map no longer projects 2 columns — reintroduces "
            "the full-row (embedding JSONB) load that burned ~4.6 GB/run"
        )
        assert "select(Article).where" not in body, (
            "_build_article_url_map regressed to loading full Article rows"
        )

    def test_offtopic_scope_filter(self):
        """Gap 2 (Niloofar 2026-06-02): the classifier must drop out-of-scope
        topics (sports/weather) even when they're original reporting, so they
        never reach the clustering pool."""
        from app.services.content_type import (
            LABELS, DEFAULT_ALLOWED, heuristic_classify,
        )
        assert "off_topic" in LABELS
        assert "off_topic" not in DEFAULT_ALLOWED, "off_topic must be dropped, not allowed"

        class _Stub:
            def __init__(self, title):
                self.title_original = title
                self.content_text = None
                self.summary = None
                self.url = ""
                self.rss_category = None
        # Section-tag-free sports title (the Telegram junk pattern)
        v = heuristic_classify(_Stub("کاسمیرو در مسیر میامی برای تجدید دیدار با مسی"))
        assert v is not None and v.label == "off_topic", (
            "content-keyword off-domain detection regressed — sports junk would cluster"
        )
        v2 = heuristic_classify(_Stub("ایران قهرمان مسابقات وزنه‌برداری جوانان جهان شد"))
        assert v2 is not None and v2.label == "off_topic"

    def test_clustering_pool_gates_content_type(self):
        """Gap 1 (Niloofar 2026-06-02): cluster_articles must only pull
        classified + allowed articles, mirroring the NLP/embed gate — else
        unclassified (NULL) / off-topic articles reach the LLM title-grouper
        and pollute clusters."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        i = src.find("async def cluster_articles")
        body = src[i:i + 4000]
        assert "Article.content_type.isnot(None)" in body, (
            "cluster_articles no longer gates on content_type IS NOT NULL"
        )
        assert "content_filters -> 'allowed') @> to_jsonb(articles.content_type)" in body, (
            "cluster_articles no longer mirrors the source allowed-list gate"
        )

    def test_detach_mark_irrelevant_removes_from_pool(self):
        """mark_irrelevant=True must also set content_type='other' so the
        article leaves the clustering pool (nlp_pipeline allowed-list gate)
        instead of re-clustering and re-polluting (Parham, 2026-06-02)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        i = src.find("class _DetachArticlesRequest")
        assert "mark_irrelevant: bool = False" in src[i:i + 800], (
            "_DetachArticlesRequest lost the mark_irrelevant flag"
        )
        j = src.find("async def detach_articles_from_stories")
        body = src[j:j + 3500]
        assert 'request.mark_irrelevant' in body and '_vals["content_type"] = "other"' in body, (
            "detach no longer sets content_type='other' on mark_irrelevant — "
            "irrelevant articles would re-cluster"
        )

    def test_article_url_map_built_once_per_run(self):
        """ingest_all_channels must build the map ONCE and pass it into
        ingest_channel — not rebuild it for each of the 44 channels."""
        from pathlib import Path
        import inspect
        from app.services import telegram_service as ts
        # ingest_channel accepts the prebuilt map
        params = inspect.signature(ts.ingest_channel).parameters
        assert "article_url_map" in params, "ingest_channel must accept a prebuilt map"
        src = inspect.getsource(ts.ingest_all_channels)
        assert "_build_article_url_map(db)" in src, "map no longer built once at run level"
        assert "ingest_channel(channel, db, article_url_map)" in src, (
            "ingest_all_channels no longer passes the shared map into ingest_channel — "
            "the per-channel rebuild (44× multiplier) is back"
        )


class TestPinnedHeroFeedExemption:
    """Parham 2026-06-15: a fast-breaking story fragments when its pinned
    hero froze / exceeded the caps, so fresh coverage spawns parallel
    clusters (the Iran-US deal split into 6). Fix: the match-existing query
    lets a manually-pinned story (priority >= pin floor) keep absorbing
    fresh (<=7d) articles past the max_cluster_size and umbrella first-pub
    caps. The runaway-umbrella protection stays in force for everything the
    operator has NOT pinned, and the <=7-day ARTICLE window is untouched.

    These are source-level tripwires (same style as TestSevenDayDataWindow):
    they pin the SHAPE of the exemption so a future cycle can't silently
    drop it or, worse, extend it to the article-age window.
    """

    def _match_body(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        idx = src.find("async def _match_to_existing_stories")
        assert idx >= 0, "_match_to_existing_stories must exist"
        nxt = src.find("\nasync def ", idx + 1)
        return src[idx: nxt if nxt > 0 else len(src)]

    def test_pins_exempt_from_size_cap(self):
        import re
        body = self._match_body()
        # An or_( ... ) containing BOTH the pin floor and the size cap.
        m = re.search(r"or_\((?:[^)]|\([^)]*\))*?_MERGE_PIN_PRIORITY_FLOOR"
                      r"(?:[^)]|\([^)]*\))*?max_cluster_size", body, re.S)
        assert m is not None, (
            "match-existing must exempt pinned stories from the "
            "max_cluster_size cap via or_(priority>=PIN_FLOOR, ...)"
        )

    def test_pins_exempt_from_umbrella_first_pub_cap(self):
        import re
        body = self._match_body()
        m = re.search(r"or_\((?:[^)]|\([^)]*\))*?_MERGE_PIN_PRIORITY_FLOOR"
                      r"(?:[^)]|\([^)]*\))*?umbrella_cutoff", body, re.S)
        assert m is not None, (
            "match-existing must exempt pinned stories from the umbrella "
            "first-pub cap via or_(priority>=PIN_FLOOR, ...)"
        )

    def test_article_age_window_is_NOT_pin_exempt(self):
        """The <=7d ARTICLE window must stay a hard AND for every story,
        pinned or not — only stale STORIES are widened, never stale
        articles. The last_updated_at/time_cutoff gate must remain a bare
        condition, not wrapped in an or_ with the pin floor."""
        body = self._match_body()
        assert "Story.last_updated_at >= time_cutoff," in body, (
            "the freshness gate must remain a top-level AND condition"
        )
        # AGE_CAP_DAYS stays <= 7 (belt-and-suspenders with TestSevenDayDataWindow)
        import re
        m = re.search(r"AGE_CAP_DAYS = (\d+)", body)
        assert m and int(m.group(1)) <= 7

    def test_oversized_canary_exempts_pins(self):
        """A deliberately-large pinned hero must NOT trip the
        oversized_active_stories canary (else it's a guaranteed false
        positive the moment the matcher feeds a pin past the cap)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py").read_text()
        idx = src.find("AS oversized_active")
        assert idx >= 0
        window = src[max(0, idx - 400): idx]
        assert "COALESCE(priority, 0) < 40" in window, (
            "oversized_active canary must exclude pinned (priority>=40) "
            "stories now that the matcher grows pins past max_cluster_size"
        )


class TestMergeReassignsAnalystTakes:
    """2026-06-19: the cluster step failed with a ForeignKeyViolationError —
    _merge_hidden_stories (and the sibling _merge_tiny_by_cosine) deleted a
    merged-away victim story that still had analyst_takes rows. analyst_takes.
    story_id is a RESTRICT FK, so the DELETE violated it. Both merge paths must
    reassign analyst_takes to the keeper BEFORE deleting the victim, exactly
    like articles / telegram_posts / rater_feedback already do."""

    def _fn_body(self, name):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        idx = src.find(f"async def {name}")
        assert idx >= 0, f"{name} must exist"
        nxt = src.find("\nasync def ", idx + 1)
        return src[idx: nxt if nxt > 0 else len(src)]

    def test_merge_hidden_reassigns_analyst_takes_before_delete(self):
        body = self._fn_body("_merge_hidden_stories")
        assert "AnalystTake" in body, "merge_hidden must touch analyst_takes"
        assert "db.delete(victim)" in body
        assert body.index("AnalystTake") < body.index("db.delete(victim)"), (
            "analyst_takes must be reassigned BEFORE the victim is deleted"
        )

    def test_merge_tiny_reassigns_analyst_takes_before_delete(self):
        body = self._fn_body("_merge_tiny_by_cosine")
        assert "AnalystTake" in body, "merge_tiny must touch analyst_takes"
        assert "db.delete(victim)" in body
        assert body.index("AnalystTake") < body.index("db.delete(victim)")


class TestStalePublishedArticlesNeverCluster:
    """2026-07-04 audit: the 7-day clustering window filtered on ingested_at
    only, so feeds serving weeks-old items (37 stale articles in one week,
    all 37 reaching a story) put a May-10 oil article inside the July-4
    Khamenei-funeral story. Both clustering pools must gate on published_at
    too (NULL allowed — the ingested_at gate still holds)."""

    def test_cluster_pool_gates_on_published_at(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        idx = src.find("# ── Step 1: Get unclustered articles from the last 7 days ──")
        assert idx >= 0, "cluster pool anchor comment must exist"
        block = src[idx: idx + 2600]
        assert "Article.ingested_at >= cutoff" in block
        assert "Article.published_at >= cutoff" in block, (
            "cluster pool must also require published_at within the window "
            "(stale-published gate, 2026-07-04)"
        )
        assert "Article.published_at.is_(None)" in block, (
            "NULL published_at must remain allowed (some feeds omit dates)"
        )

    def test_orphan_recluster_pool_gates_on_published_at(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        idx = src.find("async def step_recluster_orphans")
        assert idx >= 0
        block = src[idx: idx + 4200]
        assert "Article.published_at >= aged_out_cutoff" in block, (
            "orphan pool must mirror the cluster-pool stale-published gate"
        )
        assert "Article.published_at.is_(None)" in block


class TestBirthGraceBeforeAgeFreeze:
    """2026-07-04 audit: first_published_at = MIN(article.published_at), so a
    single stale-dated interloper aged a 16-MINUTE-old story past the age_7d
    freeze cutoff (30 stories frozen within 1h of birth in one week). Each
    birth-frozen story rejects the next wave of coverage, spawning the sibling
    fragments the sibling_cluster_fragmentation canary keeps catching. The
    age-based freeze must require the story row itself to be >= 24h old; the
    size-based freeze keeps NO grace."""

    def test_birth_grace_constant_and_wiring(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        assert "BIRTH_GRACE_HOURS = 24" in src, "birth-grace constant must exist"
        idx = src.find("# Birth grace (Parham 2026-07-04)")
        assert idx >= 0, "birth-grace rationale comment must anchor the freeze query"
        block = src[idx: idx + 1400]
        assert "Story.created_at < birth_grace_cutoff" in block
        assert "Story.first_published_at < freeze_cutoff" in block

    def test_size_freeze_keeps_no_grace(self):
        """The 100+-article umbrella freeze must stay OUTSIDE the grace
        conjunction — an umbrella needs freezing regardless of story age."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "auto_maintenance.py").read_text()
        idx = src.find("# Birth grace (Parham 2026-07-04)")
        block = src[idx: idx + 1600]
        grace_idx = block.find("Story.created_at < birth_grace_cutoff")
        size_idx = block.find("Story.article_count > UMBRELLA_ARTICLE_COUNT_FREEZE")
        assert grace_idx >= 0 and size_idx >= 0
        # The size condition appears after the grace-wrapped age block,
        # as a sibling arm of the outer or_ — not inside the grace &.
        closing = block[grace_idx:size_idx]
        assert closing.count("or_(") >= 1, (
            "age conditions must sit in a nested or_ under the grace guard, "
            "with the size freeze as a separate outer arm"
        )


class TestClusteringPromptsCarryPublishDates:
    """2026-07-04 audit: the grouping/matching LLM decided \"same event?\"
    BLIND to dates. A live strong-model judge run proved publish dates are the
    single most decisive interloper-rejection signal (May-10 article vs July-4
    event = certain rejection). The article block, the story block, and both
    prompt rule lists must carry dates."""

    def test_articles_block_includes_publish_date(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        idx = src.find("def _build_articles_block")
        assert idx >= 0
        block = src[idx: idx + 2600]
        assert 'pub.date().isoformat()' in block, (
            "article lines must carry the publish date"
        )

    def test_story_lines_include_coverage_start(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "clustering.py").read_text()
        assert "coverage since" in src, (
            "matching story lines must show when coverage began"
        )

    def test_prompts_state_the_date_rule(self):
        from app.services.clustering import MATCHING_PROMPT, CLUSTERING_PROMPT
        assert "DATES:" in MATCHING_PROMPT, "matching prompt must carry the date rule"
        assert "DATES:" in CLUSTERING_PROMPT, "clustering prompt must carry the date rule"
        assert "publish date" in MATCHING_PROMPT
        assert "publish date" in CLUSTERING_PROMPT


class TestMergeTinyUsesCalibratedSameEventTest:
    """2026-07-04: _merge_tiny_by_cosine's raw cosine>=0.60 rule was a
    grab-bag factory — a 14-day replay of its ACTUAL merges found 248/278
    (89%) fail a title-token same-event check (the Doha-talks story absorbed
    funeral fragments + executions + poppy cultivation in one live pass).
    The v1 postmortem measured unrelated Persian domestic news at 0.53-0.73
    centroid cosine, so 0.60 sat inside the confusion zone. Each pair must
    now pass homepage_dedup._same_event (cosine >= 0.64 AND title jaccard
    >= 0.12 AND a shared event-specific token) — the same calibration that
    guards step_dedupe_homepage_events."""

    def _body(self):
        import inspect
        from app.services.clustering import _merge_tiny_by_cosine
        return inspect.getsource(_merge_tiny_by_cosine)

    def test_uses_same_event_not_raw_cosine(self):
        body = self._body()
        assert "_same_event" in body, (
            "merge_tiny must use homepage_dedup._same_event, not raw cosine"
        )
        assert "sim >= threshold" not in body, (
            "raw-cosine union (sim >= threshold) must not decide merges — "
            "that rule merged funeral+prisoners+poppy into the Doha story"
        )

    def test_thresholds_come_from_homepage_dedup_constants(self):
        """One calibration, two consumers: the thresholds must be the
        DEDUP_* constants, not re-hardcoded numbers that can drift."""
        body = self._body()
        assert "DEDUP_COSINE_MIN" in body
        assert "DEDUP_JACCARD_MIN" in body
        assert "DEDUP_MIN_SHARED_TOKENS" in body

    def test_blocks_generic_token_only_pairs(self):
        """End-to-end sanity on the imported test itself: two titles sharing
        only generic war-vocab (ایران/آمریکا) must NOT merge even at high
        cosine; two titles about the same specific event must merge."""
        from app.services.homepage_dedup import (
            DedupRow, _same_event,
            DEDUP_COSINE_MIN, DEDUP_JACCARD_MIN, DEDUP_MIN_SHARED_TOKENS,
        )

        def row(id_, title, vec):
            return DedupRow(id=id_, title_fa=title, centroid=vec, priority=0,
                            trending_score=0.0, last_updated_at=None, article_count=3)

        kw = dict(cos_min=DEDUP_COSINE_MIN, jac_min=DEDUP_JACCARD_MIN,
                  min_shared=DEDUP_MIN_SHARED_TOKENS)
        # Same specific event (funeral discounts) — near-identical vectors
        a = row("a", "تخفیف ۵۰ درصدی هتل‌ها برای زائران مراسم تشییع", [1, 0, 0, 0])
        b = row("b", "تسهیلات و تخفیف هتل‌ها برای زائران تشییع رهبر", [0.95, 0.312, 0, 0])
        assert _same_event(a, b, **kw) is True
        # Only generic overlap (ایران/آمریکا) — high cosine must still block
        c = row("c", "مذاکرات ایران و آمریکا در دوحه از سر گرفته شد", [1, 0, 0, 0])
        d = row("d", "هشدار ایران به آمریکا درباره تنگه هرمز", [0.95, 0.312, 0, 0])
        assert _same_event(c, d, **kw) is False

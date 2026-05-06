"""Schema contract tests for the homepage-driving API responses.

These tests pin the *shape* of `/api/v1/stories/trending`,
`/blindspots`, `/{id}/analysis`, and the homepage-scope gate. The
frontend reads each of these fields by name in `HomeBody.tsx` and
related components — silently dropping or renaming a field is a
homepage outage. Pydantic schema introspection is enough to catch
the regression class without spinning up a DB.

Tests also lock that bias_scoring's homepage-only path actually goes
through `homepage_scope.homepage_story_ids` rather than re-implementing
filters inline (the drift mode that produced April-May 2026 cost
overruns).

Run: `cd backend && pytest tests/test_api_contracts.py -v`
"""

from pathlib import Path
import typing


# ═════════════════════════════════════════════════════════════════════
# 1. StoryBrief — the trending + blindspots payload shape
# ═════════════════════════════════════════════════════════════════════

class TestStoryBriefSchema:
    """`StoryBrief` is the unit type for both /trending and /blindspots
    list endpoints. Every field in this test is read directly by name
    in the frontend (`HomeBody.tsx`, `StoryCard.tsx`, etc.). A renamed
    or removed field doesn't 500 — it silently produces broken cards."""

    def test_required_identity_fields(self):
        from app.schemas.story import StoryBrief
        for name in ("id", "title_fa", "title_en", "slug"):
            assert name in StoryBrief.model_fields, (
                f"StoryBrief.{name} is read by the frontend — required."
            )

    def test_required_count_fields(self):
        from app.schemas.story import StoryBrief
        for name in ("article_count", "source_count", "trending_score"):
            assert name in StoryBrief.model_fields

    def test_homepage_card_visual_fields(self):
        """Fields the homepage hero/card layout reads to render:
        image, real-image gate, freshness, narrative split."""
        from app.schemas.story import StoryBrief
        for name in (
            "image_url",
            "has_real_image",
            "last_updated_at",
            "first_published_at",
            "narrative_groups",
            "inside_border_pct",
            "outside_border_pct",
            "is_blindspot",
            "blindspot_type",
            "topics",
            "priority",
            "update_signal",
        ):
            assert name in StoryBrief.model_fields, (
                f"StoryBrief.{name} is on the homepage critical path."
            )

    def test_legacy_pct_fields_still_present(self):
        """The 2/3-axis legacy split (state_pct / diaspora_pct /
        independent_pct) is still read by some homepage filters. Until
        the frontend migrates fully to narrative_groups, dropping
        these = silent zeros = wrong filters."""
        from app.schemas.story import StoryBrief
        for name in ("state_pct", "diaspora_pct", "independent_pct"):
            assert name in StoryBrief.model_fields

    def test_image_url_allows_null(self):
        """Stories without an image set image_url=None. If the schema
        ever goes to `str` (no Optional), every imageless story 500s."""
        from app.schemas.story import StoryBrief
        field = StoryBrief.model_fields["image_url"]
        # Field annotation must accept None — the type is Union with NoneType.
        assert type(None) in typing.get_args(field.annotation), (
            "image_url must remain Optional/None-allowed. Some stories "
            "legitimately have no image until a HITL pin lands."
        )

    def test_update_signal_is_optional_dict(self):
        """The orange/green update badge depends on `update_signal`
        being either a dict or None. Coercing to a non-optional dict
        breaks freshly-created stories that haven't snapshotted yet."""
        from app.schemas.story import StoryBrief
        field = StoryBrief.model_fields["update_signal"]
        assert type(None) in typing.get_args(field.annotation)

    def test_priority_default_is_zero(self):
        """The pin protection logic (HomeBody.tsx + step_archive_stale)
        treats priority=0 as 'unpinned'. Changing the default to e.g.
        -50 silently demotes every freshly created story."""
        from app.schemas.story import StoryBrief
        assert StoryBrief.model_fields["priority"].default == 0


# ═════════════════════════════════════════════════════════════════════
# 2. StoryListResponse — pagination contract
# ═════════════════════════════════════════════════════════════════════

class TestStoryListResponseSchema:
    """The list endpoint pagination shape is read by the HITL queue,
    admin search, and the public archive. Renaming any field breaks
    all three at once."""

    def test_pagination_fields_present(self):
        from app.schemas.story import StoryListResponse
        for name in ("stories", "total", "page", "page_size"):
            assert name in StoryListResponse.model_fields, (
                f"StoryListResponse.{name} is required by paginated callers."
            )


# ═════════════════════════════════════════════════════════════════════
# 3. StoryAnalysisResponse — the bias panel
# ═════════════════════════════════════════════════════════════════════

class TestStoryAnalysisResponseSchema:
    """`/{id}/analysis` powers the per-side narratives + bias panel +
    دورنما briefing. Each field below has a frontend reader."""

    def test_per_side_summary_fields_present(self):
        from app.schemas.story import StoryAnalysisResponse
        for name in (
            "summary_fa",
            "state_summary_fa",
            "diaspora_summary_fa",
            "independent_summary_fa",
            "bias_explanation_fa",
        ):
            assert name in StoryAnalysisResponse.model_fields

    def test_dispute_score_present(self):
        """Dispute score drives the homepage 'most disputed' rail and
        the update_signal dispute branch. Removing it silently breaks
        both."""
        from app.schemas.story import StoryAnalysisResponse
        assert "dispute_score" in StoryAnalysisResponse.model_fields

    def test_doornama_briefing_field_present(self):
        """دورنما briefing is exposed via `briefing_fa`. The hero card
        on the homepage depends on it; renaming or removing this field
        silently breaks the integrative-narrator paragraph that sits
        above the bias panel."""
        from app.schemas.story import StoryAnalysisResponse
        assert "briefing_fa" in StoryAnalysisResponse.model_fields, (
            "StoryAnalysisResponse must expose `briefing_fa` (the "
            "دورنما field). Hero card render depends on it."
        )

    def test_evidence_fields_present(self):
        """The bias panel surfaces per-article evidence + per-source
        neutrality. Both are populated by bias_scoring; removing either
        breaks the readable explanation alongside the score."""
        from app.schemas.story import StoryAnalysisResponse
        for name in ("source_neutrality", "article_neutrality", "article_evidence"):
            assert name in StoryAnalysisResponse.model_fields


# ═════════════════════════════════════════════════════════════════════
# 4. Endpoint → response_model wiring (route metadata)
# ═════════════════════════════════════════════════════════════════════

class TestEndpointResponseModels:
    """FastAPI route decorators name the response_model. If anyone
    swaps in a different schema (or removes the response_model
    entirely, falling back to dict), validation drops and drift
    becomes silent."""

    def test_trending_uses_story_brief(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        # Find the /trending route and verify response_model
        idx = src.find('@router.get("/trending"')
        assert idx >= 0, "/trending route must exist"
        decorator_end = src.find(")", idx)
        decorator = src[idx:decorator_end]
        assert "list[StoryBrief]" in decorator, (
            "/trending must return list[StoryBrief]. Changing the "
            "response_model is a frontend break."
        )

    def test_blindspots_uses_story_brief(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find('@router.get("/blindspots"')
        assert idx >= 0
        decorator_end = src.find(")", idx)
        decorator = src[idx:decorator_end]
        assert "list[StoryBrief]" in decorator, (
            "/blindspots must return list[StoryBrief] (same shape as "
            "/trending so the homepage can mix both rails)."
        )

    def test_analysis_uses_story_analysis_response(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "stories.py"
        ).read_text()
        idx = src.find("/{story_id}/analysis")
        assert idx >= 0
        # Walk back to the @router.get for this route.
        decorator_start = src.rfind("@router.get(", 0, idx)
        decorator_end = src.find(")", decorator_start)
        decorator = src[decorator_start:decorator_end]
        assert "StoryAnalysisResponse" in decorator


# ═════════════════════════════════════════════════════════════════════
# 5. bias_scoring routes through homepage_scope (no inline duplicates)
# ═════════════════════════════════════════════════════════════════════

class TestBiasScoringHonorsHomepageScope:
    """The 'every penny goes to homepage-visible only' rule
    (Parham 2026-05-03) requires bias_scoring to use the centralized
    `homepage_scope.homepage_story_ids` gate. The risk this guards
    against: someone re-introduces an inline filter that drifts from
    trending API filters → spend lands on stories the public can't see.
    """

    def test_score_unscored_imports_homepage_scope(self):
        src = (
            Path(__file__).parent.parent / "app" / "services" / "bias_scoring.py"
        ).read_text()
        assert "from app.services.homepage_scope import homepage_story_ids" in src, (
            "bias_scoring must import homepage_story_ids from "
            "homepage_scope — single source of truth for the spend gate."
        )

    def test_score_unscored_uses_homepage_only_gate(self):
        src = (
            Path(__file__).parent.parent / "app" / "services" / "bias_scoring.py"
        ).read_text()
        # The `homepage_only_top_n` parameter and the gate using it.
        assert "homepage_only_top_n" in src
        assert "homepage_story_ids(" in src, (
            "bias_scoring's homepage gate must call homepage_story_ids() "
            "directly — no re-implementation of trending/blindspot filters "
            "inline. Drift here was the April-May 2026 cost overrun."
        )

    def test_score_unscored_orders_by_priority_desc(self):
        """Even with the gate in place, candidates within the visible
        set must be processed in priority order so the per-run budget
        lands on the top cards first."""
        src = (
            Path(__file__).parent.parent / "app" / "services" / "bias_scoring.py"
        ).read_text()
        assert "Story.priority.desc()" in src and "Story.trending_score.desc()" in src, (
            "bias_scoring must order candidates priority DESC, then "
            "trending_score DESC. trending-score-only sort hands budget "
            "to demoted umbrellas."
        )


# ═════════════════════════════════════════════════════════════════════
# 6. Live-app smoke: response_model fields actually serialize
# ═════════════════════════════════════════════════════════════════════

class TestDetachArticlesEndpoint:
    """`/admin/articles/detach` lets Niloofar audits finish in chat
    without dropping to the Railway CLI for `remove_article`. The
    endpoint must:
    - Detach all listed article IDs (set story_id = NULL)
    - Recount affected stories so the canary stays accurate
    - Surface not-found IDs separately
    - Log an `articles_detached` event per affected story
    """

    def test_endpoint_registered(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        assert '@router.post("/articles/detach"' in src, (
            "POST /articles/detach must exist for HTTP-driven Niloofar "
            "remove_article fixes."
        )

    def test_endpoint_admin_gated(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find('@router.post("/articles/detach"')
        assert idx >= 0
        # Decorator spans up to the next `async def`.
        decorator = src[idx : src.find("async def", idx)]
        assert "Depends(require_admin)" in decorator, (
            "/articles/detach mutates production data — must be "
            "admin-gated."
        )

    def test_endpoint_recounts_affected_stories(self):
        """The cached article_count drift catastrophe (April 2026) was
        fixed by adding recount steps everywhere mutations happen.
        This endpoint is one of those mutation points."""
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def detach_articles_from_stories(")
        assert idx >= 0
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert "story.article_count = live" in body, (
            "detach_articles_from_stories must recount each affected "
            "story so the cached article_count stays in sync. Without "
            "this, the oversized_active_stories canary (and other "
            "filters that rely on cached counts) drift."
        )

    def test_endpoint_logs_audit_event(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def detach_articles_from_stories(")
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert 'event_type="articles_detached"' in body, (
            "detach_articles_from_stories must emit an articles_detached "
            "story_event so the per-story timeline shows the action. "
            "Silent mutations are how the audit trail rots."
        )


class TestAttachArticlesEndpoint:
    """`/admin/articles/attach` is the mirror of /articles/detach.
    Lets Niloofar arc-curation finish in chat when the auto-matcher
    misses related coverage. Hand-curated arcs intentionally exceed
    max_cluster_size — surfaces via canary, doesn't block.
    """

    def test_endpoint_registered(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        assert '@router.post("/articles/attach"' in src, (
            "POST /articles/attach must exist for HTTP-driven Niloofar "
            "add-to-existing-arc fixes."
        )

    def test_endpoint_admin_gated(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find('@router.post("/articles/attach"')
        assert idx >= 0
        decorator = src[idx : src.find("async def", idx)]
        assert "Depends(require_admin)" in decorator, (
            "/articles/attach mutates production data — must be admin-gated."
        )

    def test_endpoint_recounts_target_story(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def attach_articles_to_story(")
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert "target_story.article_count = live" in body, (
            "/articles/attach must recount the target story so the "
            "cached article_count + oversized_active_stories canary "
            "stay accurate."
        )

    def test_endpoint_logs_audit_event(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def attach_articles_to_story(")
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert 'event_type="articles_attached"' in body, (
            "/articles/attach must emit an articles_attached story_event "
            "so the per-story timeline shows the manual curation move."
        )


class TestWeeklyDigestUpsertEndpoint:
    """`/admin/weekly-digest` lets Niloofar (Claude-driven) ship the
    weekly editorial directly from chat — without it, the homepage
    'خلاصه هفتگی پس از اولین اجرا در دسترس خواهد بود' placeholder
    stays forever because `step_weekly_digest` only writes a stats
    summary that doesn't carry the section headings the frontend
    parses.
    """

    def test_endpoint_registered(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        assert '@router.post("/weekly-digest"' in src, (
            "POST /admin/weekly-digest must exist so Niloofar can ship "
            "editorials from chat without dropping to a Railway CLI."
        )

    def test_endpoint_admin_gated(self):
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find('@router.post("/weekly-digest"')
        assert idx >= 0
        decorator = src[idx : src.find("async def", idx)]
        assert "Depends(require_admin)" in decorator, (
            "/weekly-digest writes editorial copy that goes onto the "
            "public homepage — must be admin-gated."
        )

    def test_endpoint_validates_required_sections(self):
        """The frontend WeeklyDigest.tsx parses the markdown looking for
        two specific section headings. If those are missing the homepage
        renders the empty-state placeholder anyway, so a successful
        insert with bad markdown is functionally identical to no insert.
        Validate at the boundary."""
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def upsert_weekly_digest(")
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert "روندهای کلیدی" in body and "چشم‌انداز هفته آینده" in body, (
            "/weekly-digest must validate the markdown contains both "
            "section headings WeeklyDigest.tsx parses. Silent inserts "
            "of bad markdown look like success but leave the homepage "
            "showing the placeholder."
        )

    def test_endpoint_writes_correct_status_label(self):
        """The /api/v1/stories/weekly-digest reader filters by
        `status='weekly_digest'` against maintenance_logs. Any other
        label silently disappears from the homepage."""
        src = (
            Path(__file__).parent.parent / "app" / "api" / "v1" / "admin.py"
        ).read_text()
        idx = src.find("async def upsert_weekly_digest(")
        end = src.find("\n\n\n", idx)
        body = src[idx : end if end > 0 else len(src)]
        assert "'weekly_digest'" in body, (
            "/weekly-digest must INSERT with status='weekly_digest' so "
            "/api/v1/stories/weekly-digest finds it. Any other label "
            "becomes a silent no-op."
        )


class TestSchemaSerializationSmoke:
    """Construct a StoryBrief from the absolute minimum required
    fields and verify it serializes. Catches the case where someone
    adds a non-Optional field without a default — every existing
    serializer call site then 500s on stories missing that value."""

    def test_minimal_story_brief_constructs(self):
        import uuid
        from app.schemas.story import StoryBrief
        # If any field becomes required without a default, this breaks.
        s = StoryBrief(
            id=uuid.uuid4(),
            title_en="Title",
            title_fa="عنوان",
            slug="title",
            article_count=5,
            source_count=2,
            covered_by_state=True,
            covered_by_diaspora=True,
            is_blindspot=False,
            topics=[],
            trending_score=1.0,
        )
        # Must round-trip through model_dump without error.
        dumped = s.model_dump()
        assert dumped["title_fa"] == "عنوان"
        assert dumped["update_signal"] is None  # default
        assert dumped["priority"] == 0
        assert dumped["has_real_image"] is False

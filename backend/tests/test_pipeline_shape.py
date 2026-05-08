"""Pipeline-shape regression tests for `auto_maintenance.py` —
round 5 of survival roadmap item #9.

The maintenance pipeline is a 50+ step DAG implemented as a flat
ordered list. Subtle ordering bugs (running `cluster` before
`process`, `recalc_trending` before `archive_stale`, etc.) silently
produce stale data without crashing — exactly the failure mode the
2026-05-02 rewrite was trying to fix.

These tests pin the contract:
- Every named step in FULL_PIPELINE / INGEST_ONLY_PIPELINE has a
  defined `step_*` async function (no dangling references).
- Critical orderings hold (process → cluster → centroids →
  recluster_orphans → summarize_newly_visible → telegram_link).
- Removed steps stay removed (telegram_reassign, HOURLY_PIPELINE).

Style: source-inspection + module introspection. No DB, no mocks.

Run: `cd backend && pytest tests/test_pipeline_shape.py -v`
"""

import inspect


def _import_pipelines():
    import auto_maintenance
    return auto_maintenance


def _pipeline_keys(pipeline) -> list[str]:
    return [step[0] for step in pipeline]


def _pipeline_funcs(pipeline) -> list[str]:
    return [step[2] for step in pipeline]


# ═════════════════════════════════════════════════════════════════════
# 1. Every named step has a real function behind it
# ═════════════════════════════════════════════════════════════════════

class TestEveryStepResolves:
    """Each entry in FULL_PIPELINE / INGEST_ONLY_PIPELINE is a tuple
    (key, description, function_name). The runner uses
    `getattr(auto_maintenance, function_name)` to dispatch — a typo
    or removed function silently turns into "step skipped" at runtime.
    """

    def test_full_pipeline_function_names_resolve(self):
        m = _import_pipelines()
        for func_name in _pipeline_funcs(m.FULL_PIPELINE):
            fn = getattr(m, func_name, None)
            assert fn is not None, (
                f"FULL_PIPELINE references {func_name!r} but no such "
                f"function exists in auto_maintenance.py. The runner "
                f"will silently skip this step."
            )
            assert inspect.iscoroutinefunction(fn), (
                f"{func_name} must be an async def — pipeline runner "
                f"awaits it."
            )

    def test_ingest_only_pipeline_function_names_resolve(self):
        m = _import_pipelines()
        for func_name in _pipeline_funcs(m.INGEST_ONLY_PIPELINE):
            fn = getattr(m, func_name, None)
            assert fn is not None, (
                f"INGEST_ONLY_PIPELINE references {func_name!r} but "
                f"no such function exists."
            )
            assert inspect.iscoroutinefunction(fn)

    def test_full_pipeline_keys_unique(self):
        """Step keys are used as dict-state keys; duplicates would
        silently overwrite the prior step's status in the run report."""
        m = _import_pipelines()
        keys = _pipeline_keys(m.FULL_PIPELINE)
        assert len(keys) == len(set(keys)), (
            f"FULL_PIPELINE has duplicate step keys: "
            f"{[k for k in set(keys) if keys.count(k) > 1]}"
        )

    def test_ingest_only_pipeline_keys_unique(self):
        m = _import_pipelines()
        keys = _pipeline_keys(m.INGEST_ONLY_PIPELINE)
        assert len(keys) == len(set(keys))


# ═════════════════════════════════════════════════════════════════════
# 2. Critical orderings — the data-flow constraints
# ═════════════════════════════════════════════════════════════════════

class TestPipelineOrdering:
    """Each ordering below is a hard data-flow dependency: the later
    step reads what the earlier step writes. If reordered, the later
    step runs against stale or missing data and silently produces
    wrong output. No crash, no log line, just bad numbers."""

    def _idx(self, m, key: str) -> int:
        keys = _pipeline_keys(m.FULL_PIPELINE)
        assert key in keys, f"FULL_PIPELINE missing required step {key!r}"
        return keys.index(key)

    def test_recount_before_classify_and_process(self):
        """`recount` writes Story.article_count which downstream
        filters use. Must run before any step that reads it."""
        m = _import_pipelines()
        assert self._idx(m, "recount") < self._idx(m, "classify_content_type")
        assert self._idx(m, "recount") < self._idx(m, "process")

    def test_classify_before_process(self):
        """Content-type classification gates which articles go to NLP
        embedding (skip aggregation/other). If process runs first,
        we waste embedding budget on articles we'd later drop."""
        m = _import_pipelines()
        assert self._idx(m, "classify_content_type") < self._idx(m, "process")

    def test_process_before_cluster(self):
        """Clustering consumes article embeddings produced by process."""
        m = _import_pipelines()
        assert self._idx(m, "process") < self._idx(m, "cluster")

    def test_cluster_before_centroids(self):
        """Centroids are means over article embeddings within a story —
        cluster must attach articles first."""
        m = _import_pipelines()
        assert self._idx(m, "cluster") < self._idx(m, "centroids")

    def test_centroids_before_recluster_orphans(self):
        """recluster_orphans matches against fresh centroids."""
        m = _import_pipelines()
        assert self._idx(m, "centroids") < self._idx(m, "recluster_orphans")

    def test_recluster_before_summarize_newly_visible(self):
        """The new step_summarize_newly_visible must run AFTER
        recluster_orphans (so it can pick up stories that just crossed
        the visibility threshold via reclustering) and BEFORE
        telegram_link (so summaries are ready when posts attach)."""
        m = _import_pipelines()
        assert self._idx(m, "recluster_orphans") < self._idx(m, "summarize_newly_visible")
        assert self._idx(m, "summarize_newly_visible") < self._idx(m, "telegram_link")

    def test_recalc_trending_pre_summarize_runs_before_summarize(self):
        """Per Parham 2026-05-04: doornama hero pick must reflect
        post-ingest trending_score, not the prior cron's. The
        recalc_trending_pre_summarize step exists for exactly this."""
        m = _import_pipelines()
        assert self._idx(m, "recalc_trending_pre_summarize") < self._idx(m, "summarize")

    def test_recalc_trending_pre_summarize_runs_before_newly_visible(self):
        """Cycle-3 Phase B (2026-05-08): also before summarize_newly_visible.
        Pre-this-fix the pre-summarize recalc ran AFTER newly_visible at
        position 13, so the homepage_story_ids `trending_score > 0.5`
        gate saw the prior cron's score — silently dropping legitimately-
        newly-visible stories from the early-summarize pass."""
        m = _import_pipelines()
        assert self._idx(m, "recalc_trending_pre_summarize") < self._idx(
            m, "summarize_newly_visible"
        ), (
            "recalc_trending_pre_summarize MUST run before summarize_"
            "newly_visible — otherwise homepage_story_ids reads stale "
            "trending_score and the early-summarize pass misses stories"
        )

    def test_late_recalc_trending_runs_after_recount_after_dedup(self):
        """Cycle-3 Phase B (2026-05-08): the late recalc_trending must
        come AFTER recount_after_dedup. Pre-this-fix it ran BEFORE
        dedup_articles + flag_unrelated, so trending_score baked the
        pre-dedup article_count and stayed stale on the homepage for
        the 6h until next cron's recalc. Trending depends on
        article_count; article_count just got fixed by recount_after_
        dedup; therefore recalc must follow it."""
        m = _import_pipelines()
        keys = _pipeline_keys(m.FULL_PIPELINE)
        assert "recount_after_dedup" in keys
        assert "recalc_trending" in keys
        recount_pos = keys.index("recount_after_dedup")
        recalc_pos = keys.index("recalc_trending")
        assert recount_pos < recalc_pos, (
            f"recount_after_dedup (pos {recount_pos}) must run BEFORE "
            f"the late recalc_trending (pos {recalc_pos}). Otherwise "
            f"trending_score uses stale pre-dedup article_count."
        )

    def test_summarize_before_bias_score(self):
        """bias_score per-article scoring uses summary context; if it
        runs first, scoring lacks the cluster narrative."""
        m = _import_pipelines()
        assert self._idx(m, "summarize") < self._idx(m, "bias_score")

    def test_archive_before_demote(self):
        """Cycle-1 audit Phase B reordering (2026-05-07): archive_stale
        runs BEFORE demote so a story FRESHLY frozen by archive_stale's
        freeze pass (day-7 age trigger or article_count > 100 trigger)
        gets demoted in the same cron tick. Prior ordering left a 6h
        window where newly-frozen umbrellas stayed at priority=0 on
        the homepage. Day-30 stories that go from frozen → archived
        in archive_stale were already demoted on a prior cron's
        day-7 freeze, so demote correctly skips them now (archived_at
        filter excludes archived stories)."""
        m = _import_pipelines()
        assert self._idx(m, "archive_stale") < self._idx(m, "demote_umbrellas")

    def test_archive_before_late_recalc_trending(self):
        """The late recalc_trending must see archived_at flags so
        archived stories drop out of the trending score."""
        m = _import_pipelines()
        # The late one — there are two recalc_trending steps; we want
        # the second (post-archive). Check that archive is before AT
        # LEAST ONE recalc_trending step.
        keys = _pipeline_keys(m.FULL_PIPELINE)
        archive_pos = keys.index("archive_stale")
        # The post-archive recalc has key "recalc_trending" (no
        # _pre_summarize suffix).
        assert "recalc_trending" in keys
        recalc_pos = keys.index("recalc_trending")
        assert archive_pos < recalc_pos, (
            "archive_stale must precede the late recalc_trending so "
            "trending_score reflects newly-archived state."
        )


# ═════════════════════════════════════════════════════════════════════
# 3. Removed steps stay removed
# ═════════════════════════════════════════════════════════════════════

class TestRemovedStepsStayRemoved:
    """Steps that were removed for documented reasons. Re-introducing
    any of these is a regression — the documented reason would re-fire."""

    def test_telegram_reassign_not_in_full_pipeline(self):
        """Per CLAUDE.md verification step: telegram_reassign was
        removed 2026-05-03 due to chronic 1215s timeout every run.
        If it reappears, that's a regression — the structural failure
        wasn't fixed, it was just removed."""
        m = _import_pipelines()
        keys = _pipeline_keys(m.FULL_PIPELINE)
        funcs = _pipeline_funcs(m.FULL_PIPELINE)
        assert "telegram_reassign" not in keys, (
            "telegram_reassign was removed 2026-05-03 due to chronic "
            "1215s timeout every full-mode run. Pipeline-simplification "
            "audit confirmed structural failure (not transient). If the "
            "function needs to run again, fix the timeout root cause "
            "first; don't just re-add the broken step."
        )
        assert "step_reassign_telegram_posts" not in funcs

    def test_hourly_pipeline_constant_removed(self):
        """Per 2026-05-03: HOURLY_PIPELINE was removed because only
        FULL_PIPELINE should be on a cron. Any leftover Railway
        schedule firing 'hourly' now falls back to INGEST_ONLY_PIPELINE
        for safety. Re-introducing the constant breaks that safety."""
        m = _import_pipelines()
        assert not hasattr(m, "HOURLY_PIPELINE"), (
            "HOURLY_PIPELINE was removed 2026-05-03. If you need a "
            "different cadence, add to INGEST_ONLY_PIPELINE."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. INGEST_ONLY_PIPELINE size + content
# ═════════════════════════════════════════════════════════════════════

class TestIngestOnlyPipelineShape:
    """The 'Run Now' dashboard path uses INGEST_ONLY_PIPELINE. CLAUDE.md
    pins total_steps=12 for this mode; if the count drifts, the
    dashboard's progress bar shows wrong percentages but the run still
    completes — silent UI bug."""

    def test_full_pipeline_total_steps_is_58(self):
        """The 6h-cron progress bar pins to this count. Same drift
        risk as INGEST_ONLY — keep both this number and the parent
        `CLAUDE.md` (`full=58`) in lockstep with the actual list.

        Bumped 56 → 57 on 2026-05-07 (EN+FR rollout Phase 2):
        added `translate_homepage_visible` after `niloofar_polish_telegram`.

        Bumped 57 → 58 on 2026-05-07 evening (cycle-1 audit Phase B):
        added `recount_after_dedup` after `flag_unrelated` to fix the
        100%-of-crons drift where `dedup_articles` + `flag_unrelated`
        detached articles AFTER the early `recount` pass.
        """
        m = _import_pipelines()
        assert len(m.FULL_PIPELINE) == 58, (
            f"FULL_PIPELINE step count drifted: found "
            f"{len(m.FULL_PIPELINE)} steps. If this is intentional, "
            f"update both this test AND the parent CLAUDE.md verification "
            f"step #4 (`full=58`)."
        )

    def test_total_steps_is_13(self):
        """The Run Now dashboard progress bar pins to this count.
        If the count drifts up, the bar shows wrong percentages but
        the run still completes — silent UI bug. CLAUDE.md should
        be kept in lockstep with this number."""
        m = _import_pipelines()
        assert len(m.INGEST_ONLY_PIPELINE) == 13, (
            f"INGEST_ONLY_PIPELINE step count drifted: found "
            f"{len(m.INGEST_ONLY_PIPELINE)} steps. If this is intentional, "
            f"update both this test AND CLAUDE.md's verification step #4."
        )

    def test_required_steps_present(self):
        """The minimum viable pipeline for the dashboard 'Run Now':
        ingest → process → cluster → centroids → recluster → summarize_newly."""
        m = _import_pipelines()
        keys = _pipeline_keys(m.INGEST_ONLY_PIPELINE)
        for required in (
            "ingest",
            "process",
            "cluster",
            "centroids",
            "recluster_orphans",
            "summarize_newly_visible",
        ):
            assert required in keys, (
                f"INGEST_ONLY_PIPELINE missing critical step {required!r}. "
                f"Run Now path will produce stale data without it."
            )

    def test_ingest_only_orderings_hold(self):
        """Same data-flow constraints as FULL — process precedes
        cluster, cluster precedes centroids, etc."""
        m = _import_pipelines()
        keys = _pipeline_keys(m.INGEST_ONLY_PIPELINE)
        assert keys.index("process") < keys.index("cluster")
        assert keys.index("cluster") < keys.index("centroids")
        assert keys.index("centroids") < keys.index("recluster_orphans")
        assert keys.index("recluster_orphans") < keys.index("summarize_newly_visible")


# ═════════════════════════════════════════════════════════════════════
# 5. Pipeline starts with ingest, not something destructive
# ═════════════════════════════════════════════════════════════════════

class TestPipelineEntrypoint:
    """First-step invariant. Both pipelines must start with `ingest`
    so partial-run failures still leave the system in a state where
    re-running picks up new content. Starting with e.g.
    `archive_stale` would silently archive without ever ingesting,
    eventually emptying the homepage."""

    def test_full_starts_with_ingest(self):
        m = _import_pipelines()
        assert _pipeline_keys(m.FULL_PIPELINE)[0] == "ingest"

    def test_ingest_only_starts_with_ingest(self):
        m = _import_pipelines()
        assert _pipeline_keys(m.INGEST_ONLY_PIPELINE)[0] == "ingest"

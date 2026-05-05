"""Risk-prioritized clustering tests — round 1.

Approach: tests describe invariants that, if violated, would have
produced or did produce a known incident. Each test names the bug
class it tripwires.

Coverage gap closed: war-audit suite covered the *new* fixes from
2026-05-03/04/05 but did not pin the *pre-existing* matcher safety
constraints. Refactoring clustering.py without these tests can quietly
remove a guard rail (e.g. dropping `Story.archived_at.is_(None)` from
the WHERE) and the failure surfaces only after a homepage-empty event.

Run: `cd backend && pytest tests/test_clustering_safety.py -v`
"""

from pathlib import Path


# ═════════════════════════════════════════════════════════════════════
# Source-inspection helpers — same style as test_war_audit_fixes.py
# ═════════════════════════════════════════════════════════════════════

def _clustering_src() -> str:
    return (
        Path(__file__).parent.parent / "app" / "services" / "clustering.py"
    ).read_text()


def _maintenance_src() -> str:
    return (Path(__file__).parent.parent / "auto_maintenance.py").read_text()


def _homepage_scope_src() -> str:
    return (
        Path(__file__).parent.parent / "app" / "services" / "homepage_scope.py"
    ).read_text()


def _matcher_body() -> str:
    """Body of `_match_to_existing_stories` — the SELECT we lean on
    every clustering tick. Returned as a single string for grepping."""
    src = _clustering_src()
    idx = src.find("async def _match_to_existing_stories(")
    assert idx >= 0, "_match_to_existing_stories must exist in clustering.py"
    end = src.find("\n\nasync def ", idx + 100)
    return src[idx : end if end > 0 else len(src)]


# ═════════════════════════════════════════════════════════════════════
# 1. Threshold ladder is monotonically increasing across age tiers
# ═════════════════════════════════════════════════════════════════════

class TestEmbeddingThresholdLadder:
    """The accretion gate has three age tiers:
      0-2d   → 0.40 (fresh, easy match)
      2-5d   → 0.55 (aged, more friction)
      5-7d   → 0.65 (near-freeze, max friction)
      7d+    → frozen, refused entirely

    If anyone reorders or flattens these values, drift returns. The
    war-audit suite checks that 0.65 + 5d *exist*; this test checks the
    ladder is *ordered* — a stronger constraint."""

    def test_ladder_constants_strictly_increase(self):
        src = _clustering_src()
        # Pull each constant out of source. Tolerant to whitespace.
        import re
        def grab(name: str) -> float:
            m = re.search(rf"{name}\s*=\s*([0-9.]+)", src)
            assert m, f"{name} must be defined in clustering.py"
            return float(m.group(1))

        fresh = grab("EMBEDDING_SIM_THRESHOLD")
        aged = grab("EMBEDDING_SIM_THRESHOLD_AGED")
        near_freeze = grab("EMBEDDING_SIM_THRESHOLD_NEAR_FREEZE")

        assert fresh < aged < near_freeze, (
            f"Threshold ladder must strictly increase with age: "
            f"fresh={fresh} < aged={aged} < near_freeze={near_freeze}. "
            f"If a value is dropped or reordered, drift returns to umbrellas "
            f"approaching freeze."
        )
        # Pin the absolute values too — accidentally widening the gate
        # (e.g. fresh=0.30) silently re-opens the cluster_new spend
        # explosion seen in April 2026.
        assert fresh >= 0.40, "fresh-tier floor must not go below 0.40"
        assert near_freeze >= 0.65, "near-freeze must not go below 0.65"

    def test_age_boundaries_strictly_increase(self):
        src = _clustering_src()
        import re
        aged_days = re.search(r"AGED_CANDIDATE_DAYS\s*=\s*(\d+)", src)
        nf_days = re.search(r"NEAR_FREEZE_CANDIDATE_DAYS\s*=\s*(\d+)", src)
        umbrella_days = re.search(r"UMBRELLA_FIRST_PUB_CAP_DAYS\s*=\s*(\d+)", src)
        assert aged_days and nf_days and umbrella_days
        a, n, u = int(aged_days.group(1)), int(nf_days.group(1)), int(umbrella_days.group(1))
        assert a < n < u + 1, (
            f"Age boundaries must order: aged({a}d) < near-freeze({n}d) "
            f"< umbrella-cap({u}d). near-freeze must hit BEFORE the "
            f"umbrella refusal at {u}d so there's a tightening window."
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Matcher SELECT enforces every safety guard (frozen / archived /
#    cap / age / umbrella)
# ═════════════════════════════════════════════════════════════════════

class TestMatcherWhereClauseGuards:
    """`_match_to_existing_stories` is the SQL gate that decides which
    stories are eligible to absorb new articles. Every guard in this
    WHERE clause exists because a previous bug let the matcher return
    a story it shouldn't have. Removing one quietly is a regression.

    Each test below corresponds to a real incident or invariant from
    `project_freshness_model.md`."""

    def test_excludes_frozen_stories(self):
        body = _matcher_body()
        assert "Story.frozen_at.is_(None)" in body, (
            "Matcher SELECT must filter Story.frozen_at IS NULL. "
            "Without this, frozen umbrellas keep absorbing articles "
            "and last_updated_at gets bumped, defeating freeze. See "
            "project_freshness_model.md (May 2026 rewrite)."
        )

    def test_excludes_archived_stories(self):
        body = _matcher_body()
        assert "Story.archived_at.is_(None)" in body, (
            "Matcher SELECT must filter Story.archived_at IS NULL. "
            "F3 — archived stories are never resurrected."
        )

    def test_enforces_max_cluster_size_cap(self):
        body = _matcher_body()
        assert "Story.article_count < settings.max_cluster_size" in body, (
            "Matcher SELECT must enforce article_count < max_cluster_size "
            "to prevent unbounded umbrella growth. The 5adc903e umbrella "
            "(30 articles spanning unrelated topics) shows what happens "
            "when the cap is bypassed."
        )

    def test_enforces_visibility_floor(self):
        body = _matcher_body()
        assert "Story.article_count >= 5" in body, (
            "Matcher must only consider stories with article_count >= 5. "
            "Below that the cluster isn't visible enough to anchor matches."
        )

    def test_enforces_age_cap_via_last_updated_at(self):
        """AGE_CAP_DAYS = 10. Stories untouched for >10 days should
        not absorb new articles even if otherwise eligible (no
        thread-zombie resurrection)."""
        body = _matcher_body()
        assert "AGE_CAP_DAYS" in body, (
            "Matcher must define AGE_CAP_DAYS to prevent zombie-thread "
            "resurrection — straggling articles attaching to dead stories."
        )
        assert "Story.last_updated_at >= time_cutoff" in body, (
            "Matcher SELECT must filter on last_updated_at against the "
            "stricter of legacy_cutoff or fresh_cutoff."
        )

    def test_enforces_umbrella_first_published_cap(self):
        """UMBRELLA_FIRST_PUB_CAP_DAYS = 7. Even if a story's
        last_updated_at is fresh (because someone keeps adding articles
        every day), refuse to grow it past 7d-by-creation. NULL
        first_published_at falls back to created_at — the loophole
        Parham closed 2026-05-03."""
        body = _matcher_body()
        assert "UMBRELLA_FIRST_PUB_CAP_DAYS" in body, (
            "Matcher must define UMBRELLA_FIRST_PUB_CAP_DAYS to bound "
            "umbrella growth by creation date, not just activity."
        )
        # The NULL-fallback to created_at is the load-bearing 2026-05-03
        # closure — without it, NULL-dated zombie stories absorb articles.
        assert "func.coalesce(Story.first_published_at, Story.created_at)" in body, (
            "Umbrella cap must use coalesce(first_published_at, created_at) "
            "so NULL-dated stories still get gated. This loophole was "
            "closed 2026-05-03 — do not re-introduce a bare "
            "`first_published_at >= cutoff` clause."
        )


# ═════════════════════════════════════════════════════════════════════
# 3. step_recluster_orphans applies the SAME gates as the matcher
# ═════════════════════════════════════════════════════════════════════

class TestReclusterOrphansHasSameGates:
    """Per project_freshness_model.md (root cause #2 of the 2026-05-02
    rewrite): step_recluster_orphans was bypassing the matcher's gates
    entirely, letting orphans attach to umbrella stories and bumping
    their last_updated_at (which defeated freeze). The fix added the
    same filters to recluster_orphans. If anyone re-loosens this step,
    freeze breaks again."""

    def test_recluster_orphans_filters_frozen(self):
        src = _maintenance_src()
        idx = src.find("async def step_recluster_orphans(")
        assert idx >= 0
        end = src.find("\n\nasync def ", idx + 100)
        body = src[idx : end if end > 0 else len(src)]
        assert "frozen_at" in body and "is_(None)" in body, (
            "step_recluster_orphans must filter Story.frozen_at IS NULL. "
            "Without this, orphan recluster bypasses the freeze rule "
            "and umbrellas keep growing. Root cause #2 of the 2026-05-02 "
            "rewrite — do not re-introduce."
        )

    def test_recluster_orphans_filters_archived(self):
        src = _maintenance_src()
        idx = src.find("async def step_recluster_orphans(")
        end = src.find("\n\nasync def ", idx + 100)
        body = src[idx : end if end > 0 else len(src)]
        assert "archived_at" in body, (
            "step_recluster_orphans must filter Story.archived_at — "
            "archived stories are never resurrected."
        )

    def test_recluster_orphans_caps_attach_budget(self):
        """The third 2026-05-02 fix (commit 9e519fb): track per-story
        attach budget so a single fresh story can't absorb the entire
        500-orphan batch in one pass (story grew from 25 to 196+
        articles before this fix)."""
        src = _maintenance_src()
        idx = src.find("async def step_recluster_orphans(")
        end = src.find("\n\nasync def ", idx + 100)
        body = src[idx : end if end > 0 else len(src)]
        # The fix reports skipped_capacity_exhausted in stats.
        assert "capacity_exhausted" in body or "attach_budget" in body, (
            "step_recluster_orphans must track per-story attach budget "
            "to prevent single-pass overflow. See commit 9e519fb."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. Small-target stories require signal overlap (drift prevention)
# ═════════════════════════════════════════════════════════════════════

class TestSmallTargetSignalRequirement:
    """When a candidate story has < 10 articles, its centroid is
    fragile — a single off-topic article can dominate vocabulary and
    pull in further off-topic articles via cosine alone. The fix:
    raise the cosine floor to 0.45 AND require at least one concrete
    signal overlap (jaccard ≥ 0.15, shared quote, or shared number).

    Catches the drift pattern where small clusters got hijacked by
    weakly-related articles riding generic vocabulary."""

    def test_small_target_threshold_raised(self):
        body = _matcher_body()
        # The small-target branch should set a tighter base_threshold
        # than the fresh-tier 0.40 baseline.
        assert "target_small" in body, (
            "Matcher must distinguish small-target (article_count < 10) "
            "stories — their centroid is too fragile for the standard "
            "fresh-tier threshold."
        )
        assert "base_threshold = 0.45" in body, (
            "Small-target stories must use base_threshold = 0.45 (not "
            "the default 0.40) — fragile-centroid drift defense."
        )

    def test_small_target_requires_signal_overlap(self):
        body = _matcher_body()
        # The small-target signal check must use jaccard or quote/number
        # overlap. If ALL of these disappear, drift returns.
        assert "_jaccard" in body, "Matcher must use _jaccard for token overlap"
        assert "a_quotes" in body and "a_numbers" in body, (
            "Small-target signal check must compare quotes and numbers, "
            "not just tokens — high-precision overlap signals."
        )


# ═════════════════════════════════════════════════════════════════════
# 5. homepage_scope is the single source of truth for spend gating
# ═════════════════════════════════════════════════════════════════════

class TestHomepageScopeContract:
    """`homepage_scope.homepage_story_ids` mirrors the trending and
    blindspot APIs *exactly*. Drift between this gate and the API is
    the failure mode that produced the April-May 2026 cost overruns
    (LLM spend flowed to stories the public couldn't see).

    These tests pin the contract: if you change a filter here, you must
    change it in api/v1/stories.py too — and these tests fail to flag
    the missed half."""

    def test_trending_excludes_archived_not_frozen(self):
        """Per Parham 2026-05-03: frozen stories STAY on the homepage
        (sorted behind active via priority=-50). Archived stories are
        retired. The trending query must filter archived but NOT frozen."""
        src = _homepage_scope_src()
        idx = src.find("trending_q = (")
        end = src.find("ids = ", idx)
        block = src[idx:end]
        assert "archived_at.is_(None)" in block, (
            "Trending filter must exclude archived stories."
        )
        # The frozen-stays-visible rule is load-bearing. If anyone adds
        # `frozen_at.is_(None)` here, the homepage will go bare on a
        # quiet day (the 2026-05-03 catastrophe).
        assert "frozen_at" not in block, (
            "Trending filter MUST NOT exclude frozen stories. "
            "Frozen means 'no new articles can join' — NOT 'leaves "
            "homepage'. Re-introducing this filter caused the empty-"
            "homepage incident on 2026-05-03. See project_freshness_model.md."
        )

    def test_blindspot_has_recency_window(self):
        """Blindspot stories get a 14d soft window — older one-sided
        coverage is interesting for archive but not 'currently a
        blindspot'. If this window is dropped, the blindspot rail
        fills with year-old stories nobody cares about."""
        src = _homepage_scope_src()
        assert "BLINDSPOT_LAST_UPDATED_DAYS" in src, (
            "Blindspot scope must have a recency cutoff constant."
        )
        idx = src.find("blindspot_q = (")
        end = src.find("ids |= ", idx)
        block = src[idx:end]
        assert "last_updated_at >= cutoff" in block, (
            "Blindspot filter must enforce the recency window — "
            "stale one-sided coverage is not a current blindspot."
        )

    def test_eligible_filters_excludes_hidden_priority(self):
        """`homepage_eligible_filters()` is used as a SQL-side filter
        when materializing the full top-N is too expensive. It must
        exclude priority <= -100 (hidden) but NOT priority = -50
        (demoted-but-visible)."""
        src = _homepage_scope_src()
        idx = src.find("def homepage_eligible_filters(")
        # Inspect only the return-tuple body, not the docstring (which
        # explicitly explains why frozen_at is NOT in the filter).
        return_idx = src.find("return", idx)
        end = src.find("\n\n", return_idx)
        body = src[return_idx : end if end > 0 else len(src)]
        assert "Story.priority > -100" in body, (
            "homepage_eligible_filters must use `priority > -100` so "
            "demoted (-50) stories remain eligible. Anything stricter "
            "(e.g. `priority >= 0`) hides demoted stories from the "
            "homepage entirely, breaking the frozen-stays-visible rule."
        )
        assert "frozen_at" not in body, (
            "homepage_eligible_filters MUST NOT mention frozen_at in "
            "its return tuple — frozen stories stay homepage-eligible "
            "(Parham 2026-05-03)."
        )


# ═════════════════════════════════════════════════════════════════════
# 6. The BATCH_SIZE / MAX_CLUSTER_ATTEMPTS sanity bounds
# ═════════════════════════════════════════════════════════════════════

class TestClusteringSafetyBounds:
    """Sanity bounds on clustering's headline numbers. These rarely
    change but if they do, the clustering tick can either OOM (batch
    too large), spend forever in retries (attempts unbounded), or
    skip work silently (batch = 0)."""

    def test_batch_size_in_safe_range(self):
        import re
        m = re.search(r"^BATCH_SIZE\s*=\s*(\d+)", _clustering_src(), re.M)
        assert m
        n = int(m.group(1))
        assert 10 <= n <= 500, (
            f"BATCH_SIZE = {n} is out of safe range (10-500). "
            f"Too small starves the LLM batch endpoint; too large "
            f"OOMs the worker on long article bodies."
        )

    def test_max_cluster_attempts_bounded(self):
        import re
        m = re.search(r"^MAX_CLUSTER_ATTEMPTS\s*=\s*(\d+)", _clustering_src(), re.M)
        assert m
        n = int(m.group(1))
        assert 1 <= n <= 5, (
            f"MAX_CLUSTER_ATTEMPTS = {n} is out of safe range (1-5). "
            f"Above 5, a poison article can stall the queue indefinitely."
        )

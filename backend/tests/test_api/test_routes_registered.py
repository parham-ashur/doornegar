"""Route-registration tests.

These don't call the app — they just introspect `app.routes` to guarantee
every API path we document in CLAUDE.md is actually wired up. Catches
renames, accidental deletions, and typos during refactors.

No DB, no LLM, no network — safe to run in CI.
"""

from app.main import app


def _registered_paths() -> set[str]:
    return {r.path for r in app.routes if hasattr(r, "path")}


def test_public_api_routes_exist():
    """The public routes promised in CLAUDE.md must all be registered."""
    expected = {
        "/health",
        "/api/v1/sources",
        "/api/v1/sources/{slug}",
        "/api/v1/articles",
        "/api/v1/stories",
        "/api/v1/stories/trending",
        "/api/v1/stories/blindspots",
        "/api/v1/stories/{story_id}",
        "/api/v1/social/channels",
        "/api/v1/social/stories/{story_id}/social",
        "/api/v1/social/stories/{story_id}/sentiment/history",
    }
    paths = _registered_paths()
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"


def test_admin_pipeline_routes_exist():
    """Admin pipeline endpoints must remain callable after refactors."""
    expected = {
        "/api/v1/admin/pipeline/run-all",
        "/api/v1/admin/ingest/trigger",
        "/api/v1/admin/nlp/trigger",
        "/api/v1/admin/cluster/trigger",
        "/api/v1/admin/bias/trigger",
    }
    paths = _registered_paths()
    missing = expected - paths
    assert not missing, f"Missing admin routes: {missing}"


def test_telegram_analysis_cache_endpoints_exist():
    """The TTL-cache endpoints we added this audit round must stay wired."""
    paths = _registered_paths()
    assert "/api/v1/social/stories/{story_id}/telegram-analysis" in paths
    assert "/api/v1/social/stories/{story_id}/telegram-analysis/invalidate" in paths


def test_fetch_stats_endpoints_exist():
    """Admin dashboard fetch-stats + per-channel drilldown must stay wired."""
    paths = _registered_paths()
    assert "/api/v1/admin/sources/stats" in paths
    assert "/api/v1/admin/channels/stats" in paths
    assert "/api/v1/social/channels/{channel_id}/posts" in paths
    # is_active toggle endpoints
    assert "/api/v1/admin/sources/{slug}" in paths
    assert "/api/v1/admin/channels/{channel_id}" in paths

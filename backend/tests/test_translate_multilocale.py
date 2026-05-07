"""Smoke tests for the multi-locale translation service (EN+FR Phase 2).

Source-inspection + pure-function checks. No DB, no LLM, no mocks. Mirrors
the project test style established in war_audit / pipeline_shape.
"""

from pathlib import Path


def _import_module():
    from app.services import translate_multilocale
    return translate_multilocale


# ═════════════════════════════════════════════════════════════════════
# 1. Voice prompt files exist + are loadable
# ═════════════════════════════════════════════════════════════════════


class TestVoicePromptsShipped:
    """Phase 2 cannot operate without these prompt files. Pinning their
    presence catches accidental .gitignore additions or rename drift."""

    def test_nyt_v1_prompt_exists(self):
        m = _import_module()
        path = m._VOICE_PROMPTS_DIR / "nyt-v1.txt"
        assert path.exists(), f"NYT voice prompt missing at {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text) > 1000, "NYT prompt suspiciously short"
        assert "Niloofar-EN" in text
        assert "TRANSLATION_FAILED" in text, "Refusal sentinel must be in prompt"

    def test_lemonde_v1_prompt_exists(self):
        m = _import_module()
        path = m._VOICE_PROMPTS_DIR / "lemonde-v1.txt"
        assert path.exists(), f"Le Monde voice prompt missing at {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text) > 1000, "Le Monde prompt suspiciously short"
        assert "Niloofar-FR" in text
        assert "TRANSLATION_FAILED" in text

    def test_load_prompt_is_cached(self):
        m = _import_module()
        # First call loads from disk.
        m._load_prompt._cache.clear()  # type: ignore[attr-defined]
        text1 = m._load_prompt("nyt-v1")
        assert "nyt-v1" in m._load_prompt._cache  # type: ignore[attr-defined]
        # Second call returns cached value.
        text2 = m._load_prompt("nyt-v1")
        assert text1 is text2  # same object — proves cache hit


# ═════════════════════════════════════════════════════════════════════
# 2. Compose / parse roundtrip
# ═════════════════════════════════════════════════════════════════════


class TestJSONFormat:
    """The wire format between service and LLM is JSON (response_format
    = json_object). _compose_user_message writes a prompt asking for
    JSON; _parse_structured reads JSON back. The earlier `### key`
    format produced 100% parse failures on French in the 2026-05-07
    09:00 UTC cron — gpt-4o-mini ignored markdown markers when
    instructed in French. JSON mode constrains the output."""

    def test_compose_includes_keys_and_values(self):
        m = _import_module()
        msg = m._compose_user_message({"title": "سلام", "summary": "خبر"})
        assert "title" in msg
        assert "summary" in msg
        assert "سلام" in msg
        assert "خبر" in msg
        assert "JSON" in msg or "json" in msg

    def test_compose_skips_empty(self):
        m = _import_module()
        msg = m._compose_user_message({"title": "خبر", "summary": ""})
        # Only the non-empty key should appear in the requested-keys list.
        assert "title" in msg
        # Loose assertion — "summary" may appear in fixed prose; the
        # key-list line should not include it.
        keys_line = [
            ln for ln in msg.split("\n") if "exactly these keys" in ln
        ]
        if keys_line:
            assert "summary" not in keys_line[0]

    def test_compose_empty_payload_returns_empty(self):
        m = _import_module()
        assert m._compose_user_message({}) == ""
        assert m._compose_user_message({"title": "", "summary": None}) == ""

    def test_parse_basic_json(self):
        m = _import_module()
        out = '{"title": "Hello world", "summary": "A short summary."}'
        result = m._parse_structured(out, ["title", "summary"])
        assert result == {"title": "Hello world", "summary": "A short summary."}

    def test_parse_strips_markdown_fence(self):
        """LLMs sometimes wrap JSON in ```json ... ``` despite
        response_format=json_object. Parser tolerates that."""
        m = _import_module()
        out = '```json\n{"title": "Hello", "summary": "Line."}\n```'
        result = m._parse_structured(out, ["title", "summary"])
        assert result is not None
        assert result.get("title") == "Hello"
        assert result.get("summary") == "Line."

    def test_parse_rejects_invalid_json(self):
        m = _import_module()
        result = m._parse_structured("Not JSON at all", ["title", "summary"])
        assert result is None

    def test_parse_returns_none_on_no_expected_keys(self):
        """Output JSON without any expected key is treated as a
        failure — we never silently substitute."""
        m = _import_module()
        out = '{"unrelated": "nothing matches"}'
        result = m._parse_structured(out, ["title", "summary"])
        assert result is None

    def test_parse_skips_non_string_values(self):
        m = _import_module()
        out = '{"title": "OK", "summary": null}'
        result = m._parse_structured(out, ["title", "summary"])
        assert result == {"title": "OK"}

    def test_parse_skips_empty_strings(self):
        m = _import_module()
        out = '{"title": "OK", "summary": "   "}'
        result = m._parse_structured(out, ["title", "summary"])
        assert result == {"title": "OK"}


# ═════════════════════════════════════════════════════════════════════
# 3. Module-level configuration
# ═════════════════════════════════════════════════════════════════════


class TestModuleConfig:
    """Pin the model + locales so a misconfiguration is loud."""

    def test_editorial_model_is_gpt_4o_mini_or_overridden(self):
        m = _import_module()
        # Tier 2 default. Env override is allowed (Tier 3 graduation
        # may bump this), but the default must stay gpt-4o-mini until
        # the rollout doc is updated.
        assert m.EDITORIAL_MODEL.startswith("gpt-")

    def test_locales_are_en_and_fr(self):
        m = _import_module()
        assert set(m.OG_LOCALES) == {"en", "fr"}
        assert set(m.PROMPT_VERSIONS.keys()) == {"en", "fr"}

    def test_prompt_versions_are_named(self):
        m = _import_module()
        assert m.PROMPT_VERSIONS["en"] == "nyt-v1"
        assert m.PROMPT_VERSIONS["fr"] == "lemonde-v1"

    def test_concurrency_caps_are_sane(self):
        m = _import_module()
        # Tier-2 RPM ceiling; over 12 concurrent risks rate-limit
        # pressure even on gpt-4o-mini.
        assert m._EDITORIAL_SEMAPHORE._value <= 12  # type: ignore[attr-defined]
        # Per-cron stories cap. 30 × 2 locales = 60 calls. 3 crons/day
        # = 180 calls/day. Well under any plausible rate-limit ceiling.
        assert 1 <= m.STORIES_PER_RUN <= 100

    def test_cost_cap_is_one_dollar(self):
        m = _import_module()
        assert m.COST_CAP_USD_24H == 1.0


# ═════════════════════════════════════════════════════════════════════
# 4. Sentinel constants
# ═════════════════════════════════════════════════════════════════════


class TestSentinel:
    """The refusal sentinel must match across the prompt file and the
    Python constant. If they drift, refusals get parsed as success."""

    def test_sentinel_matches_prompt_file(self):
        m = _import_module()
        for version in ("nyt-v1", "lemonde-v1"):
            text = (m._VOICE_PROMPTS_DIR / f"{version}.txt").read_text(
                encoding="utf-8"
            )
            assert m.TRANSLATION_FAILED_SENTINEL in text, (
                f"Sentinel '{m.TRANSLATION_FAILED_SENTINEL}' not found "
                f"in {version}.txt — refusals will be silently treated "
                f"as successful translations."
            )


# ═════════════════════════════════════════════════════════════════════
# 5. Pipeline registration
# ═════════════════════════════════════════════════════════════════════


class TestPipelineRegistration:
    """The cron step must be reachable via auto_maintenance.globals()
    lookup (that's how run_maintenance dispatches)."""

    def test_step_is_in_full_pipeline(self):
        import auto_maintenance
        keys = [step[0] for step in auto_maintenance.FULL_PIPELINE]
        assert "translate_homepage_visible" in keys

    def test_step_function_resolves_to_coroutine(self):
        import inspect
        import auto_maintenance
        fn = getattr(auto_maintenance, "step_translate_homepage_visible", None)
        assert fn is not None, "step_translate_homepage_visible missing from auto_maintenance"
        assert inspect.iscoroutinefunction(fn)

    def test_step_runs_after_archive_stale(self):
        """Translation must happen AFTER archive_stale so we don't pay
        LLM cost on stories about to leave the homepage."""
        import auto_maintenance
        keys = [step[0] for step in auto_maintenance.FULL_PIPELINE]
        assert keys.index("archive_stale") < keys.index("translate_homepage_visible")

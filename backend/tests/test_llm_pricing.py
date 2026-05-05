"""Tests for `app/services/llm_pricing.py` — round 9 of survival
roadmap item #9.

The cost dashboard's accuracy hinges on this module. Bugs surface as
silently-wrong costs — the dashboard reports $0.10/day when it should
be $1.00, monthly projection underestimates, $30 cap is breached
quietly. Three failure classes:

1. Snapshot-model pricing: OpenAI ships dated snapshots like
   `gpt-4o-mini-2024-07-18` — must resolve to `gpt-4o-mini` rates.
2. Cached-input math: `prompt_tokens_details.cached_tokens` is a
   SUBSET of `prompt_tokens`, not in addition. Double-billing here
   inflates dashboard numbers. Under-billing hides real cost.
3. Unknown-model handling: must return zeros (not crash) so the
   call still gets logged and an operator sees the gap.

Run: `cd backend && pytest tests/test_llm_pricing.py -v`
"""

from app.services.llm_pricing import (
    _match_prefix,
    get_rates,
    estimate_cost,
    pricing_table,
    unknown_models_seen,
)


# ═════════════════════════════════════════════════════════════════════
# 1. _match_prefix — exact + longest-prefix matching
# ═════════════════════════════════════════════════════════════════════

class TestMatchPrefix:
    def test_exact_match(self):
        assert _match_prefix("gpt-4o-mini") == "gpt-4o-mini"
        assert _match_prefix("gpt-5") == "gpt-5"

    def test_dated_snapshot_resolves_to_base(self):
        """OpenAI snapshots like `gpt-4o-mini-2024-07-18` must use
        the `gpt-4o-mini` rate. This is the load-bearing case —
        without it, every snapshot logs $0 cost."""
        assert _match_prefix("gpt-4o-mini-2024-07-18") == "gpt-4o-mini"
        assert _match_prefix("gpt-5-mini-2026-01-15") == "gpt-5-mini"

    def test_longest_prefix_wins(self):
        """Both `gpt-4o` and `gpt-4o-mini` are in the table.
        `gpt-4o-mini` must win for `gpt-4o-mini-2024-07-18` —
        otherwise the cheaper variant gets the expensive 4o rate."""
        # gpt-4o-mini at $0.15 input vs gpt-4o at $2.50 input.
        rate = get_rates("gpt-4o-mini-2024-07-18")
        assert rate[0] == 0.15, (
            "Snapshot must resolve to longest prefix match — got "
            f"{rate[0]} which is the gpt-4o rate, not gpt-4o-mini."
        )

    def test_unknown_model_returns_none(self):
        assert _match_prefix("gpt-99-omega") is None
        assert _match_prefix("claude-opus") is None

    def test_embedding_model_resolves(self):
        assert _match_prefix("text-embedding-3-small") == "text-embedding-3-small"


# ═════════════════════════════════════════════════════════════════════
# 2. get_rates — table lookup with logging side effect
# ═════════════════════════════════════════════════════════════════════

class TestGetRates:
    def test_known_model_returns_three_tuple(self):
        rates = get_rates("gpt-4o-mini")
        assert rates == (0.15, 0.075, 0.60)

    def test_unknown_returns_none(self):
        assert get_rates("nonexistent-model-xyz") is None

    def test_unknown_recorded_in_seen_set(self):
        # First call — adds to _UNKNOWN_MODELS.
        get_rates("totally-fake-model-abc")
        assert "totally-fake-model-abc" in unknown_models_seen()

    def test_embedding_output_rate_zero(self):
        """Embeddings have no output tokens — output rate must be 0
        so estimate_cost doesn't billion-by-zero on output_tokens=0."""
        rates = get_rates("text-embedding-3-small")
        assert rates[2] == 0.0

    def test_pro_models_have_no_cached_rate(self):
        """Some pro models (gpt-5-pro, gpt-5.4-pro) don't support
        prompt caching. cached_rate must be None — caller falls
        back to input_rate."""
        rates = get_rates("gpt-5-pro")
        assert rates[1] is None


# ═════════════════════════════════════════════════════════════════════
# 3. estimate_cost — the load-bearing math
# ═════════════════════════════════════════════════════════════════════

class TestEstimateCost:
    """Every cost number on the dashboard comes from this function.
    The formula:

      uncached = max(input_tokens - cached_tokens, 0)
      input_cost  = uncached × input_rate / 1M
      cached_cost = cached × cached_rate / 1M  (or input_rate if None)
      output_cost = output × output_rate / 1M
      total = input_cost + cached_cost + output_cost

    The subtle bit: `cached_input_tokens` is a SUBSET of
    `input_tokens`, not in addition. OpenAI's
    response.usage.prompt_tokens_details.cached_tokens is a fraction
    of prompt_tokens. Double-counting here inflates costs."""

    def test_simple_call_no_caching(self):
        # 1M input @ $0.15 → $0.15
        out = estimate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
        assert out["input_cost"] == 0.15
        assert out["cached_cost"] == 0.0
        assert out["output_cost"] == 0.0
        assert out["total_cost"] == 0.15

    def test_cached_subset_not_double_counted(self):
        """1000 input tokens, 600 of them cached. Must charge:
          400 uncached × $0.15/M
          600 cached   × $0.075/M
        NOT 1000 × $0.15 + 600 × $0.075 (double-counting)."""
        out = estimate_cost(
            "gpt-4o-mini",
            input_tokens=1000,
            cached_input_tokens=600,
        )
        # 400 × 0.15 / 1M + 600 × 0.075 / 1M
        expected = (400 * 0.15 + 600 * 0.075) / 1_000_000.0
        assert abs(out["total_cost"] - expected) < 1e-9, (
            f"Cached-token math wrong: expected {expected}, got "
            f"{out['total_cost']}. Cached must be subtracted from "
            f"input before billing the uncached portion."
        )

    def test_cached_capped_at_input(self):
        """Defensive: if the LLM API returns cached > input (shouldn't
        happen, but…), the cached count must not exceed input total
        — otherwise uncached goes negative and accounting breaks."""
        out = estimate_cost(
            "gpt-4o-mini",
            input_tokens=100,
            cached_input_tokens=10_000,
        )
        # All 100 input tokens billed at cached rate; nothing extra.
        assert out["input_cost"] == 0.0  # uncached portion is zero
        assert out["cached_cost"] > 0
        assert out["total_cost"] > 0

    def test_pro_model_caches_at_input_rate(self):
        """When cached_rate is None (pro models), we charge cached
        tokens at the regular input rate — the LLM still spends them."""
        out = estimate_cost(
            "gpt-5-pro",
            input_tokens=1_000_000,
            cached_input_tokens=500_000,
        )
        # All 1M tokens × $15/M (no discount applied to the 500k)
        assert abs(out["total_cost"] - 15.0) < 1e-6

    def test_output_cost_separate(self):
        out = estimate_cost(
            "gpt-4o-mini",
            input_tokens=0,
            output_tokens=1_000_000,
        )
        # 1M output × $0.60/M = $0.60
        assert out["output_cost"] == 0.60

    def test_unknown_model_returns_zero_cost(self):
        """Per the docstring: caller still logs the call so usage
        appears in dashboard. Cost row is 0.0 with rate_source=None
        until pricing is added."""
        out = estimate_cost("unknown-model-x", input_tokens=1000, output_tokens=500)
        assert out["total_cost"] == 0.0
        assert out["rate_source"] is None

    def test_rate_source_records_resolved_prefix(self):
        """Dashboard surfaces rate_source so an operator can see how
        a snapshot got priced. The resolved prefix must appear here."""
        out = estimate_cost("gpt-4o-mini-2024-07-18", input_tokens=1000)
        assert out["rate_source"] == "gpt-4o-mini"

    def test_zero_tokens_zero_cost(self):
        out = estimate_cost("gpt-4o-mini")  # all defaults are 0
        assert out["total_cost"] == 0.0

    def test_none_tokens_handled(self):
        """OpenAI's usage object can have None for token counts on
        rare empty responses. Must not crash."""
        out = estimate_cost(
            "gpt-4o-mini",
            input_tokens=None,
            output_tokens=None,
            cached_input_tokens=None,
        )
        assert out["total_cost"] == 0.0


# ═════════════════════════════════════════════════════════════════════
# 4. pricing_table — dashboard reference view
# ═════════════════════════════════════════════════════════════════════

class TestPricingTable:
    def test_returns_list_of_dicts(self):
        rows = pricing_table()
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_includes_used_models(self):
        rows = pricing_table()
        models = {r["model"] for r in rows}
        # Models we actually call — comments mark them **USED**.
        for required in (
            "gpt-4o-mini",          # bias_scoring, story_analysis baseline
            "gpt-5-mini",           # story_analysis premium
            "gpt-4.1-nano",         # translation
            "text-embedding-3-small",  # embeddings
        ):
            assert required in models, (
                f"pricing_table missing {required!r} — it's actively "
                f"used in production. Cost dashboard would show $0 "
                f"for every call."
            )

    def test_required_keys_per_row(self):
        rows = pricing_table()
        for r in rows:
            assert "model" in r
            assert "input_per_1m" in r
            assert "output_per_1m" in r
            assert "cached_input_per_1m" in r

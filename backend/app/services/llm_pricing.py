"""OpenAI pricing table + cost estimator.

Prices per 1M tokens, USD. Mirrors the standard (non-batch, non-priority)
tier on platform.openai.com/docs/pricing as of 2026-04-21. Update when
OpenAI changes their rates.

Models we actually call are marked **USED** in a comment. The rest are
listed so the dashboard can still attribute cost if we switch models.
"""

from __future__ import annotations

# (input, cached_input, output) — dollars per 1M tokens
_PRICING: dict[str, tuple[float, float | None, float]] = {
    # GPT-5.4 family
    "gpt-5.4":       (2.50, 0.25,  15.00),
    "gpt-5.4-mini":  (0.75, 0.075, 4.50),
    "gpt-5.4-nano":  (0.20, 0.02,  1.25),
    "gpt-5.4-pro":   (30.00, None, 180.00),
    # GPT-5 family
    "gpt-5":         (1.25, 0.125, 10.00),
    "gpt-5-mini":    (0.25, 0.025, 2.00),   # **USED** (story_analysis premium, telegram pass 2 premium)
    "gpt-5-nano":    (0.05, 0.005, 0.40),
    "gpt-5-pro":     (15.00, None, 120.00),
    "gpt-5.1":       (1.25, 0.125, 10.00),
    "gpt-5.2":       (1.75, 0.175, 14.00),
    "gpt-5.2-pro":   (21.00, None, 168.00),
    # GPT-4.1 family
    "gpt-4.1":       (2.00, 0.50,  8.00),
    "gpt-4.1-mini":  (0.40, 0.10,  1.60),
    "gpt-4.1-nano":  (0.10, 0.025, 0.40),   # **USED** (translation_model, telegram pass 1, fact extraction)
    # GPT-4o family
    "gpt-4o":        (2.50, 1.25,  10.00),
    "gpt-4o-mini":   (0.15, 0.075, 0.60),   # **USED** (bias_scoring, story_analysis baseline, telegram pass 0/2 baseline)
    # Reasoning models
    "o4-mini":       (1.10, 0.275, 4.40),
    "o3":            (2.00, 0.50,  8.00),
    "o3-mini":       (1.10, 0.55,  4.40),
    "o3-pro":        (20.00, None, 80.00),
    "o1":            (15.00, 7.50, 60.00),
    "o1-mini":       (1.10, 0.55,  4.40),
    "o1-pro":        (150.00, None, 600.00),
    # Embeddings — output is zero; priced by input only.
    "text-embedding-3-small": (0.02, None, 0.0),   # **USED**
    "text-embedding-3-large": (0.13, None, 0.0),
    "text-embedding-ada-002": (0.10, None, 0.0),
}

# Track models we've failed to price so the fallback doesn't spam the log
_UNKNOWN_MODELS: set[str] = set()


def _match_prefix(model: str) -> str | None:
    """Find the longest pricing-table key that prefixes `model`.

    OpenAI ships snapshots like `gpt-4o-mini-2024-07-18` that should use
    the `gpt-4o-mini` rate. We try an exact match first, then fall back
    to the longest matching prefix so dated snapshots are priced
    automatically without us updating the dict every release.
    """
    if model in _PRICING:
        return model
    candidates = [k for k in _PRICING if model.startswith(k + "-") or model.startswith(k)]
    if not candidates:
        return None
    return max(candidates, key=len)


def get_rates(model: str) -> tuple[float, float | None, float] | None:
    """Return (input, cached_input, output) per-1M-token rates for `model`.

    Returns None when we can't price the model — caller should record the
    call with zero cost so usage still appears in the dashboard, but flag
    the row so we notice and add pricing.
    """
    key = _match_prefix(model)
    if key is None:
        if model not in _UNKNOWN_MODELS:
            _UNKNOWN_MODELS.add(model)
        return None
    return _PRICING[key]


def estimate_cost(
    model: str,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict:
    """Return {input_cost, cached_cost, output_cost, total_cost, rate_source}.

    All costs in USD. `rate_source` is the prefix used from the pricing
    table (e.g. the snapshot `gpt-4o-mini-2024-07-18` resolves to
    `gpt-4o-mini`). When the model can't be priced, all costs are 0.0
    and rate_source is None — the caller still logs the call so we
    can fix pricing without losing data.

    cached_input_tokens are counted IN ADDITION TO input_tokens in the
    OpenAI usage response (response.usage.prompt_tokens_details.cached_tokens
    is a subset of prompt_tokens). We charge them at the cached rate and
    bill the remainder at the uncached rate.
    """
    rates = get_rates(model)
    if rates is None:
        return {
            "input_cost": 0.0, "cached_cost": 0.0, "output_cost": 0.0,
            "total_cost": 0.0, "rate_source": None,
        }
    input_rate, cached_rate, output_rate = rates

    # Defensive — cached can never exceed total input
    cached = min(cached_input_tokens or 0, input_tokens or 0)
    uncached = max((input_tokens or 0) - cached, 0)

    input_cost = uncached * input_rate / 1_000_000.0
    cached_cost = cached * (cached_rate if cached_rate is not None else input_rate) / 1_000_000.0
    output_cost = (output_tokens or 0) * output_rate / 1_000_000.0

    return {
        "input_cost": round(input_cost, 6),
        "cached_cost": round(cached_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + cached_cost + output_cost, 6),
        "rate_source": _match_prefix(model),
    }


def pricing_table() -> list[dict]:
    """Serialise the pricing dict for the dashboard reference view."""
    rows = []
    for model, (inp, cached, out) in _PRICING.items():
        rows.append({
            "model": model,
            "input_per_1m": inp,
            "cached_input_per_1m": cached,
            "output_per_1m": out,
        })
    return rows


def unknown_models_seen() -> list[str]:
    """Models we've been asked about but couldn't price. Surface in the
    dashboard so an operator knows which entries to add."""
    return sorted(_UNKNOWN_MODELS)

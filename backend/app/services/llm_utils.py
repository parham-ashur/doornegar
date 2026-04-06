"""Shared LLM utilities with cost tracking.

Tracks token usage and estimated cost for every API call.
Costs based on GPT-4o-mini pricing (as of 2025):
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# Running totals for the current session
_session_stats = {
    "total_calls": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
    "session_start": datetime.now(timezone.utc).isoformat(),
}

# GPT-4o-mini pricing per token
PRICING = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000},
}


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


def get_session_stats() -> dict:
    """Get running cost stats for the current session."""
    return {**_session_stats}


async def call_llm(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> LLMResponse:
    """Call LLM with cost tracking. Prefers OpenAI, falls back to Anthropic."""
    global _session_stats

    if settings.openai_api_key:
        return await _call_openai(prompt, system, max_tokens, temperature)
    elif settings.anthropic_api_key:
        return await _call_anthropic(prompt, system, max_tokens, temperature)
    else:
        raise RuntimeError("No LLM API key configured")


async def _call_openai(
    prompt: str, system: str | None, max_tokens: int, temperature: float
) -> LLMResponse:
    import openai

    model = "gpt-4o-mini"
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    text = response.choices[0].message.content or ""
    input_tokens = response.usage.prompt_tokens if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0

    pricing = PRICING.get(model, PRICING["gpt-4o-mini"])
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]

    _session_stats["total_calls"] += 1
    _session_stats["total_input_tokens"] += input_tokens
    _session_stats["total_output_tokens"] += output_tokens
    _session_stats["total_cost_usd"] += cost

    logger.info(
        f"LLM call: {model} | {input_tokens}+{output_tokens} tokens | ${cost:.4f} | "
        f"session total: ${_session_stats['total_cost_usd']:.4f}"
    )

    return LLMResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        model=model,
    )


async def _call_anthropic(
    prompt: str, system: str | None, max_tokens: int, temperature: float
) -> LLMResponse:
    import anthropic

    model = settings.bias_scoring_model
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    msg = await client.messages.create(**kwargs)

    text = msg.content[0].text
    input_tokens = msg.usage.input_tokens
    output_tokens = msg.usage.output_tokens

    pricing = PRICING.get(model, PRICING["claude-haiku-4-5-20251001"])
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]

    _session_stats["total_calls"] += 1
    _session_stats["total_input_tokens"] += input_tokens
    _session_stats["total_output_tokens"] += output_tokens
    _session_stats["total_cost_usd"] += cost

    logger.info(
        f"LLM call: {model} | {input_tokens}+{output_tokens} tokens | ${cost:.4f}"
    )

    return LLMResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        model=model,
    )


def parse_json_response(text: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON: {text[:200]}")
        return None

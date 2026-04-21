"""Record every OpenAI call into llm_usage_logs.

The public entry point is `log_llm_usage(...)`. Every chat-completion
or embedding call site adds exactly one line after the API call. A DB
hiccup here must NEVER break the caller — everything is wrapped in a
best-effort try/except.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.database import async_session
from app.models.llm_usage import LLMUsageLog
from app.services.llm_pricing import estimate_cost

logger = logging.getLogger(__name__)


def _extract_token_counts(usage: Any) -> tuple[int, int, int]:
    """Pull (prompt, cached, completion) from an OpenAI usage object.

    Accepts three shapes:
    - chat.completions: obj with .prompt_tokens + .completion_tokens,
      and .prompt_tokens_details.cached_tokens for cached-input.
    - embeddings: obj with .prompt_tokens + .total_tokens (no completion)
    - dict with the same keys (Anthropic or tests)
    """
    if usage is None:
        return 0, 0, 0

    def _get(obj: Any, key: str, default: int = 0) -> int:
        if isinstance(obj, dict):
            return int(obj.get(key, default) or 0)
        return int(getattr(obj, key, default) or 0)

    prompt = _get(usage, "prompt_tokens") or _get(usage, "input_tokens")
    completion = _get(usage, "completion_tokens") or _get(usage, "output_tokens")

    cached = 0
    details = None
    if isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
    else:
        details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = _get(details, "cached_tokens")

    return prompt, cached, completion


async def log_llm_usage(
    *,
    model: str,
    purpose: str,
    usage: Any = None,
    input_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = None,
    story_id: uuid.UUID | str | None = None,
    article_id: uuid.UUID | str | None = None,
    meta: dict | None = None,
) -> None:
    """Record one LLM call.

    Either pass `usage` (an OpenAI response.usage object or dict) or pass
    the raw token counts directly. Cost is estimated from the pricing
    table at write time.

    Never raises — DB problems are swallowed and logged at WARN.
    """
    try:
        if usage is not None:
            p, c, o = _extract_token_counts(usage)
            in_tok = p
            cached_tok = c
            out_tok = o
        else:
            in_tok = int(input_tokens or 0)
            cached_tok = int(cached_input_tokens or 0)
            out_tok = int(output_tokens or 0)

        cost = estimate_cost(
            model=model,
            input_tokens=in_tok,
            cached_input_tokens=cached_tok,
            output_tokens=out_tok,
        )

        def _as_uuid(v):
            if v is None:
                return None
            if isinstance(v, uuid.UUID):
                return v
            try:
                return uuid.UUID(str(v))
            except Exception:
                return None

        row = LLMUsageLog(
            model=model,
            purpose=purpose,
            input_tokens=in_tok,
            cached_input_tokens=cached_tok,
            output_tokens=out_tok,
            input_cost=cost["input_cost"],
            cached_cost=cost["cached_cost"],
            output_cost=cost["output_cost"],
            total_cost=cost["total_cost"],
            story_id=_as_uuid(story_id),
            article_id=_as_uuid(article_id),
            priced=cost["rate_source"] is not None,
            meta=meta,
        )

        async with async_session() as db:
            db.add(row)
            await db.commit()
    except Exception as e:
        logger.warning(f"log_llm_usage failed ({purpose}/{model}): {e}")

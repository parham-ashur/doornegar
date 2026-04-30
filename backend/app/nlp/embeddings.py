"""Embedding generation via OpenAI text-embedding-3-small.

Uses OpenAI's embedding API instead of local sentence-transformers.
Benefits:
- Excellent multilingual quality (Persian + English + mixed)
- No PyTorch/sentence-transformers dependency (~2 GB saved)
- Consistent output on any compute host (Railway, OVH, local)
- Cost: ~$0.02/M tokens ≈ $0.05/month at Doornegar's scale

Dimensions: 384 (matching the old sentence-transformers output
so existing stored embeddings remain compatible).

Failure policy:
  A transient OpenAI error used to silently return a zero-filled
  vector, which then passed downstream as a "valid" embedding and
  collapsed every cosine comparison to 0 — breaking the story matcher
  and forcing every article into cluster_new. The current policy:
    - retry with exponential backoff
    - on final failure, split the batch and retry each half
    - a single item that still fails after all retries returns None
  Callers must treat None as "do not overwrite" and leave the
  article's embedding column unchanged.
"""

import logging
import time

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 384  # reduced from the model's native 1536

# Retry knobs — tuned for OpenAI's transient 5xx + rate-limit profile.
# 5 tries with 1/2/4/8/16s backoff = 31s total worst case. Bumped from
# 3 attempts (7s total) on 2026-04-30 after observing a 31% NULL rate
# over 24h vs 8% over 7d — most failures looked retry-shaped.
# RateLimitError specifically gets a flat 60s wait (no exponential)
# because OpenAI's 429s often come with a 60s reset window that
# 1/2/4/8/16 backoffs never cleanly clear.
_RETRY_ATTEMPTS = 5
_RETRY_BASE_DELAY_SEC = 1.0
_RATE_LIMIT_WAIT_SEC = 60.0


def _openai_client():
    from openai import OpenAI
    return OpenAI(api_key=settings.openai_api_key)


def _call_with_retry(client, inputs, *, attempts: int = _RETRY_ATTEMPTS):
    """Invoke the embeddings API with exponential backoff.

    Returns the OpenAI response on success. Raises the last exception
    on failure after `attempts` tries. Keep the retry inside this
    helper so higher-level code doesn't need to know the policy.
    """
    try:
        from openai import RateLimitError as _RLE
    except Exception:
        _RLE = None
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=inputs,
                dimensions=EMBEDDING_DIMENSIONS,
            )
        except Exception as e:
            last_exc = e
            if i < attempts - 1:
                # 60s flat wait for explicit rate limits, otherwise
                # exponential 1/2/4/8/16s.
                if _RLE is not None and isinstance(e, _RLE):
                    delay = _RATE_LIMIT_WAIT_SEC
                else:
                    delay = _RETRY_BASE_DELAY_SEC * (2 ** i)
                logger.warning(
                    f"OpenAI embeddings attempt {i + 1}/{attempts} failed "
                    f"({type(e).__name__}): {str(e)[:200]} — retrying in {delay}s"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"OpenAI embeddings attempt {i + 1}/{attempts} failed "
                    f"({type(e).__name__}): {str(e)[:200]}"
                )
    raise last_exc  # type: ignore[misc]


def generate_embedding(text: str) -> list[float] | None:
    """Generate an embedding vector for a single text via OpenAI API.

    Returns None if the API key is missing or all retries fail. A
    None return signals "unknown" and must leave any pre-existing
    stored embedding untouched — never overwrite with zeros.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping embedding")
        return None

    text = text[:8000]  # ~8k tokens for Persian — stays under the API's 8192 cap
    try:
        response = _call_with_retry(_openai_client(), text)
    except Exception:
        return None
    return response.data[0].embedding


def generate_embeddings_batch(
    texts: list[str], batch_size: int = 100
) -> list[list[float] | None]:
    """Generate embeddings for multiple texts in batches.

    Returns a list aligned 1:1 with the input `texts`. Each entry is
    either a 384-dim vector or `None` when the call failed after all
    retries. Callers MUST treat None as "skip — do not overwrite."
    """
    if not texts:
        return []

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping embeddings")
        return [None for _ in texts]

    client = _openai_client()
    out: list[list[float] | None] = []

    for start in range(0, len(texts), batch_size):
        batch = [t[:8000] for t in texts[start:start + batch_size]]
        out.extend(_embed_batch_with_split(client, batch))
    return out


def _embed_batch_with_split(client, batch: list[str]) -> list[list[float] | None]:
    """Try a batch with retry; on failure, split in half recursively.

    Splitting isolates a single poison input (rare — e.g. OpenAI
    policy rejection on a specific string) to one None instead of
    corrupting the whole batch. Down to size 1 we just give up and
    return None for that single item.
    """
    try:
        response = _call_with_retry(client, batch)
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]
    except Exception as e:
        if len(batch) == 1:
            logger.error(f"Embedding failed for single item after retries: {e}")
            return [None]
        mid = len(batch) // 2
        logger.warning(
            f"Embedding batch of {len(batch)} failed after retries — splitting into "
            f"{mid} + {len(batch) - mid}"
        )
        return (
            _embed_batch_with_split(client, batch[:mid])
            + _embed_batch_with_split(client, batch[mid:])
        )


def cosine_similarity(embedding_a: list[float], embedding_b: list[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(embedding_a)
    b = np.array(embedding_b)
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def cosine_similarity_matrix(embeddings: list[list[float]]) -> np.ndarray:
    """Compute pairwise cosine similarity matrix."""
    matrix = np.array(embeddings)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix_normed = matrix / norms
    return matrix_normed @ matrix_normed.T

"""Embedding generation via OpenAI text-embedding-3-small.

Uses OpenAI's embedding API instead of local sentence-transformers.
Benefits:
- Excellent multilingual quality (Persian + English + mixed)
- No PyTorch/sentence-transformers dependency (~2 GB saved)
- Consistent output on any compute host (Railway, OVH, local)
- Cost: ~$0.02/M tokens ≈ $0.05/month at Doornegar's scale

Dimensions: 384 (matching the old sentence-transformers output
so existing stored embeddings remain compatible).
"""

import logging

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 384  # reduced from the model's native 1536


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for a single text via OpenAI API."""
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero embedding")
        return [0.0] * EMBEDDING_DIMENSIONS

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    # Truncate to ~8000 tokens max (OpenAI limit is 8191 for this model)
    text = text[:30000]  # rough char limit; the API handles tokenization

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def generate_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Generate embeddings for multiple texts in batches.

    OpenAI's embedding API accepts up to 2048 inputs per call.
    We batch at 100 to keep request sizes manageable.
    """
    if not texts:
        return []

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero embeddings")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = [t[:30000] for t in texts[start:start + batch_size]]
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            # Response data is ordered by index
            sorted_data = sorted(response.data, key=lambda d: d.index)
            all_embeddings.extend([d.embedding for d in sorted_data])
        except Exception as e:
            logger.error(f"OpenAI embedding batch failed: {e}")
            # Return zero vectors for this batch so the pipeline doesn't crash
            all_embeddings.extend([[0.0] * EMBEDDING_DIMENSIONS for _ in batch])

    return all_embeddings


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

"""Sentence embedding generation for article similarity and clustering.

Uses the multilingual MiniLM model to generate embeddings that work
across both Persian and English articles, enabling cross-lingual
story clustering.
"""

import logging

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-load the model to avoid slow imports at startup
_model = None


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {settings.embedding_model}")
            _model = SentenceTransformer(settings.embedding_model)
            logger.info("Embedding model loaded successfully")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Install with: pip install -e '.[nlp]'"
            )
    return _model


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dim embedding vector for the given text.

    Args:
        text: The text to embed (title + body excerpt).

    Returns:
        List of 384 floats representing the text embedding.
    """
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def generate_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently.

    Args:
        texts: List of texts to embed.
        batch_size: Number of texts to process at once.

    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []

    model = _get_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
    )
    return [emb.tolist() for emb in embeddings]


def cosine_similarity(embedding_a: list[float], embedding_b: list[float]) -> float:
    """Compute cosine similarity between two embeddings.

    Since embeddings are normalized, this is just the dot product.
    """
    a = np.array(embedding_a)
    b = np.array(embedding_b)
    return float(np.dot(a, b))


def cosine_similarity_matrix(embeddings: list[list[float]]) -> np.ndarray:
    """Compute pairwise cosine similarity matrix.

    Args:
        embeddings: List of normalized embedding vectors.

    Returns:
        NxN numpy array of cosine similarities.
    """
    matrix = np.array(embeddings)
    # For normalized vectors, cosine similarity = dot product
    return matrix @ matrix.T

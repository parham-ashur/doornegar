"""Sentence embedding generation for article similarity and clustering.

For MVP deployment (without PyTorch/sentence-transformers), uses
sklearn TF-IDF vectorization as a lightweight alternative.
When sentence-transformers is available, uses the multilingual MiniLM model.
"""

import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded models
_st_model = None
_tfidf_vectorizer = None
_use_sentence_transformers = None


def _check_sentence_transformers() -> bool:
    """Check if sentence-transformers is available."""
    global _use_sentence_transformers
    if _use_sentence_transformers is not None:
        return _use_sentence_transformers
    try:
        import sentence_transformers  # noqa: F401
        _use_sentence_transformers = True
        logger.info("sentence-transformers available — using neural embeddings")
    except ImportError:
        _use_sentence_transformers = False
        logger.info("sentence-transformers not installed — using TF-IDF embeddings (lightweight)")
    return _use_sentence_transformers


def _get_st_model():
    """Lazy-load the sentence-transformers model."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _st_model = SentenceTransformer(settings.embedding_model)
    return _st_model


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    if _check_sentence_transformers():
        model = _get_st_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    else:
        # TF-IDF fallback — returns sparse vector converted to dense
        global _tfidf_vectorizer
        if _tfidf_vectorizer is None:
            _tfidf_vectorizer = TfidfVectorizer(max_features=384)
        vec = _tfidf_vectorizer.fit_transform([text]).toarray()[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


def generate_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate embeddings for multiple texts."""
    if not texts:
        return []

    if _check_sentence_transformers():
        model = _get_st_model()
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=batch_size)
        return [emb.tolist() for emb in embeddings]
    else:
        # TF-IDF fallback
        vectorizer = TfidfVectorizer(max_features=384)
        matrix = vectorizer.fit_transform(texts).toarray()
        # Normalize rows
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        matrix = matrix / norms
        return [row.tolist() for row in matrix]


def cosine_similarity(embedding_a: list[float], embedding_b: list[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(embedding_a)
    b = np.array(embedding_b)
    return float(np.dot(a, b))


def cosine_similarity_matrix(embeddings: list[list[float]]) -> np.ndarray:
    """Compute pairwise cosine similarity matrix."""
    matrix = np.array(embeddings)
    return matrix @ matrix.T

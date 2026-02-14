"""
Embedding Service
=================
Handles text embedding using sentence-transformers.
Loaded once at startup and shared across requests.
"""

import logging
from functools import lru_cache
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialise the embedding model (singleton)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _model = SentenceTransformer(settings.embedding_model)
        logger.info("Embedding model loaded")
    return _model


def embed_query(text: str) -> list[float]:
    """Embed a single text string (e.g., a user query)."""
    model = get_embedding_model()
    embedding = model.encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed multiple texts in a batch."""
    model = get_embedding_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()

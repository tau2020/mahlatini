"""
Vector Store Service
====================
Qdrant client for semantic search over the Mahlatini knowledge base.
"""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

from app.config import settings
from app.services.embeddings import embed_query

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """Get or initialise the Qdrant client (singleton)."""
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        logger.info(f"Connected to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
    return _client


def search_knowledge_base(
    query: str,
    top_k: int = None,
    category_filter: Optional[str] = None,
    destination_filter: Optional[str] = None,
    score_threshold: float = 0.3,
) -> list[dict]:
    """
    Semantic search over the Mahlatini knowledge base.

    Args:
        query: User's question
        top_k: Number of results to return
        category_filter: Optional filter by content category
        destination_filter: Optional filter by destination country
        score_threshold: Minimum similarity score

    Returns:
        List of matching chunks with scores and metadata
    """
    if top_k is None:
        top_k = settings.rag_top_k

    client = get_qdrant_client()
    query_vector = embed_query(query)

    # Build optional filters
    conditions = []
    if category_filter:
        conditions.append(FieldCondition(
            key="category",
            match=MatchValue(value=category_filter),
        ))
    if destination_filter:
        conditions.append(FieldCondition(
            key="destination_country",
            match=MatchValue(value=destination_filter),
        ))

    search_filter = Filter(must=conditions) if conditions else None

    try:
        results = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            {
                "score": hit.score,
                "text": hit.payload.get("text", ""),
                "source_url": hit.payload.get("source_url", ""),
                "page_title": hit.payload.get("page_title", ""),
                "category": hit.payload.get("category", ""),
                "destination_country": hit.payload.get("destination_country"),
                "section_heading": hit.payload.get("section_heading"),
            }
            for hit in results
        ]
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}")
        return []


def get_collection_info() -> dict:
    """Get collection statistics."""
    try:
        client = get_qdrant_client()
        info = client.get_collection(settings.qdrant_collection)
        return {
            "name": settings.qdrant_collection,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value if info.status else "unknown",
        }
    except Exception as e:
        logger.error(f"Failed to get collection info: {e}")
        return {"name": settings.qdrant_collection, "status": "error", "error": str(e)}

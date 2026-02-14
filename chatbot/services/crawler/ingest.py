"""
Mahlatini Qdrant Ingestion
==========================
Embeds content chunks and stores them in Qdrant vector database.
"""

import os
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    OptimizersConfigDiff,
    HnswConfigDiff,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    Filter,
    FieldCondition,
    MatchValue,
)
from tqdm import tqdm

from chunker import ContentChunk

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "mahlatini_kb")
DEFAULT_HOST = os.environ.get("QDRANT_HOST", "localhost")
DEFAULT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
DEFAULT_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DEFAULT_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "384"))
BATCH_SIZE = 64


class QdrantIngestor:
    """Handles embedding and storing chunks in Qdrant."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        collection: str = DEFAULT_COLLECTION,
        model_name: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
    ):
        self.client = QdrantClient(host=host, port=port)
        self.collection = collection
        self.dimension = dimension

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded")

    def ensure_collection(self):
        """Create the collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]

        if self.collection not in collections:
            logger.info(f"Creating collection: {self.collection}")
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=200,
                    full_scan_threshold=10000,
                ),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        quantile=0.99,
                        always_ram=True,
                    )
                ),
            )
            logger.info(f"Collection '{self.collection}' created")
        else:
            logger.info(f"Collection '{self.collection}' already exists")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        embeddings = self.model.encode(
            texts,
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def ingest_chunks(self, chunks: list[ContentChunk], clear_existing: bool = False):
        """
        Embed and store chunks in Qdrant.

        Args:
            chunks: List of content chunks to ingest
            clear_existing: If True, delete all existing points first
        """
        self.ensure_collection()

        if clear_existing:
            logger.warning("Clearing existing collection data")
            self.client.delete_collection(self.collection)
            self.ensure_collection()

        total = len(chunks)
        logger.info(f"Ingesting {total} chunks into Qdrant")

        # Process in batches
        for batch_start in tqdm(range(0, total, BATCH_SIZE), desc="Embedding & storing"):
            batch = chunks[batch_start : batch_start + BATCH_SIZE]

            # Embed
            texts = [chunk.text for chunk in batch]
            embeddings = self.embed_texts(texts)

            # Create Qdrant points
            points = []
            for i, (chunk, embedding) in enumerate(zip(batch, embeddings)):
                point_id = batch_start + i
                payload = {
                    "text": chunk.text,
                    "content_hash": chunk.content_hash,
                    **chunk.metadata,
                }
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                ))

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection,
                points=points,
            )

        # Get final stats
        info = self.client.get_collection(self.collection)
        logger.info(
            f"Ingestion complete. Collection '{self.collection}': "
            f"{info.points_count} points, "
            f"{info.vectors_count} vectors"
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
        destination_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for similar content (used for testing the ingestion).

        Args:
            query: Search query text
            top_k: Number of results to return
            category_filter: Optional category to filter by
            destination_filter: Optional destination to filter by
        """
        query_embedding = self.embed_texts([query])[0]

        # Build filters
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

        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=top_k,
        )

        return [
            {
                "score": hit.score,
                "text": hit.payload.get("text", ""),
                "source_url": hit.payload.get("source_url", ""),
                "page_title": hit.payload.get("page_title", ""),
                "category": hit.payload.get("category", ""),
                "destination_country": hit.payload.get("destination_country"),
            }
            for hit in results
        ]

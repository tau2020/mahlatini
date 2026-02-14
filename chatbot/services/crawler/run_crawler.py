"""
Mahlatini Crawler Runner
========================
Orchestrates the full pipeline: parse → chunk → embed → store.
"""

import os
import sys
import logging
import argparse

from dotenv import load_dotenv

from parser import parse_website
from chunker import chunk_documents
from ingest import QdrantIngestor

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("crawler")


def main():
    parser = argparse.ArgumentParser(description="Mahlatini Knowledge Base Crawler")
    parser.add_argument(
        "--website-dir",
        default=os.environ.get("WEBSITE_MIRROR_PATH", "/data/website"),
        help="Path to the HTTrack website mirror directory",
    )
    parser.add_argument(
        "--qdrant-host",
        default=os.environ.get("QDRANT_HOST", "localhost"),
        help="Qdrant server hostname",
    )
    parser.add_argument(
        "--qdrant-port",
        type=int,
        default=int(os.environ.get("QDRANT_PORT", "6333")),
        help="Qdrant server port",
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("QDRANT_COLLECTION", "mahlatini_kb"),
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing collection before ingesting",
    )
    parser.add_argument(
        "--test-search",
        type=str,
        default=None,
        help="Run a test search query after ingestion",
    )
    args = parser.parse_args()

    # Validate website directory
    if not os.path.isdir(args.website_dir):
        logger.error(f"Website directory not found: {args.website_dir}")
        sys.exit(1)

    # Step 1: Parse
    logger.info("=" * 60)
    logger.info("STEP 1: Parsing website HTML files")
    logger.info("=" * 60)
    documents = parse_website(args.website_dir)

    if not documents:
        logger.error("No valid documents found. Check the website directory.")
        sys.exit(1)

    # Log category breakdown
    categories = {}
    for doc in documents:
        categories[doc.category] = categories.get(doc.category, 0) + 1
    logger.info("Category breakdown:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {count}")

    # Step 2: Chunk
    logger.info("=" * 60)
    logger.info("STEP 2: Chunking documents")
    logger.info("=" * 60)
    chunks = chunk_documents(documents)

    # Step 3: Embed & Store
    logger.info("=" * 60)
    logger.info("STEP 3: Embedding and storing in Qdrant")
    logger.info("=" * 60)
    ingestor = QdrantIngestor(
        host=args.qdrant_host,
        port=args.qdrant_port,
        collection=args.collection,
    )
    ingestor.ingest_chunks(chunks, clear_existing=args.clear)

    # Optional: Test search
    if args.test_search:
        logger.info("=" * 60)
        logger.info(f"TEST SEARCH: '{args.test_search}'")
        logger.info("=" * 60)
        results = ingestor.search(args.test_search, top_k=3)
        for i, r in enumerate(results, 1):
            logger.info(
                f"\n--- Result {i} (score: {r['score']:.3f}) ---\n"
                f"Title: {r['page_title']}\n"
                f"Source: {r['source_url']}\n"
                f"Category: {r['category']}\n"
                f"Text: {r['text'][:200]}..."
            )

    logger.info("=" * 60)
    logger.info("CRAWLER PIPELINE COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

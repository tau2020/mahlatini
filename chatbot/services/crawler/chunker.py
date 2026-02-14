"""
Mahlatini Content Chunker
=========================
Splits parsed documents into chunks optimised for embedding and retrieval,
preserving section boundaries and enriching with metadata.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import xxhash
from langchain_text_splitters import RecursiveCharacterTextSplitter

from parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class ContentChunk:
    """A single chunk ready for embedding and storage."""
    text: str
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = xxhash.xxh64(self.text.encode()).hexdigest()


# Category-specific chunking strategies
CHUNK_CONFIGS = {
    "default": {"chunk_size": 800, "chunk_overlap": 150},
    "review": {"chunk_size": 1200, "chunk_overlap": 100},    # keep reviews whole
    "lodge": {"chunk_size": 600, "chunk_overlap": 100},      # more granular for lodges
    "itinerary": {"chunk_size": 600, "chunk_overlap": 100},  # per-day is shorter
    "policy": {"chunk_size": 500, "chunk_overlap": 50},      # precise retrieval
    "blog": {"chunk_size": 1000, "chunk_overlap": 150},      # longer form content
}


def get_splitter(category: str) -> RecursiveCharacterTextSplitter:
    """Get a text splitter configured for the content category."""
    config = CHUNK_CONFIGS.get(category, CHUNK_CONFIGS["default"])
    return RecursiveCharacterTextSplitter(
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        separators=["\n\n", "\n", ". ", ", ", " "],
        length_function=len,
        is_separator_regex=False,
    )


def chunk_document(doc: ParsedDocument) -> list[ContentChunk]:
    """
    Split a parsed document into chunks with enriched metadata.

    Strategy:
    - If document has clearly defined sections, chunk section-by-section
    - If sections are too large, split them further
    - If document has no sections, use the full content with recursive splitting
    """
    chunks = []
    splitter = get_splitter(doc.category)
    base_metadata = {
        "source_url": doc.source_url,
        "page_title": doc.page_title,
        "category": doc.category,
        "destination_country": doc.destination_country,
        "destination_region": doc.destination_region,
    }

    if doc.meta_description:
        base_metadata["meta_description"] = doc.meta_description

    if doc.content_sections and len(doc.content_sections) > 1:
        # Chunk by sections
        for section_idx, section in enumerate(doc.content_sections):
            section_text = f"{section['heading']}\n\n{section['content']}"
            section_metadata = {
                **base_metadata,
                "section_heading": section["heading"],
                "section_index": section_idx,
            }

            config = CHUNK_CONFIGS.get(doc.category, CHUNK_CONFIGS["default"])
            if len(section_text) <= config["chunk_size"] * 1.2:
                # Section fits in a single chunk
                chunks.append(ContentChunk(
                    text=section_text,
                    metadata={**section_metadata, "chunk_index": len(chunks)},
                ))
            else:
                # Section needs splitting
                sub_chunks = splitter.split_text(section_text)
                for sub_text in sub_chunks:
                    chunks.append(ContentChunk(
                        text=sub_text,
                        metadata={**section_metadata, "chunk_index": len(chunks)},
                    ))
    else:
        # No clear sections — split the full content
        text_chunks = splitter.split_text(doc.content)
        for idx, text in enumerate(text_chunks):
            chunks.append(ContentChunk(
                text=text,
                metadata={**base_metadata, "chunk_index": idx},
            ))

    # Add total chunk count to each chunk's metadata
    total = len(chunks)
    for chunk in chunks:
        chunk.metadata["total_chunks"] = total

    return chunks


def chunk_documents(documents: list[ParsedDocument]) -> list[ContentChunk]:
    """Process multiple documents into chunks."""
    all_chunks = []
    for doc in documents:
        doc_chunks = chunk_document(doc)
        all_chunks.extend(doc_chunks)

    logger.info(
        f"Chunked {len(documents)} documents into {len(all_chunks)} chunks "
        f"(avg {len(all_chunks) / max(len(documents), 1):.1f} chunks/doc)"
    )
    return all_chunks

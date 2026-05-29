"""document_chunker — split extracted text into overlapping chunks for the vector store.

Usage::

    from tools.document_chunker import chunk

    chunks = chunk(text, source_file="report.pdf", metadata={"pages": 10})
    # Each chunk: { text, chunk_index, total_chunks, source_file, metadata }
"""
from __future__ import annotations

import re
from typing import Any


# Sentence boundary pattern: period/bang/question followed by space or newline
_SENTENCE_END = re.compile(r"(?<=[.!?])(?=\s)")


def _split_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries, returning sentence fragments."""
    return _SENTENCE_END.split(text)


def chunk(
    text: str,
    source_file: str,
    metadata: dict[str, Any] | None = None,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[dict[str, Any]]:
    """Split text into overlapping chunks.

    Args:
        text:        Full extracted text.
        source_file: Origin file path (stored on each chunk).
        metadata:    Extra metadata propagated to every chunk.
        chunk_size:  Target character length per chunk.
        overlap:     Characters carried forward from previous chunk.

    Returns:
        List of chunk dicts: { text, chunk_index, total_chunks, source_file, metadata }
    """
    if not text or not text.strip():
        return []

    meta = dict(metadata or {})
    sentences = _split_sentences(text)

    chunks: list[str] = []
    current = ""
    carry = ""  # overlap tail from previous chunk

    for sentence in sentences:
        candidate = carry + current + sentence
        if len(candidate) <= chunk_size:
            current += sentence
        else:
            # Flush current chunk if non-empty
            if current.strip():
                chunks.append(carry + current)
            # Start new chunk; carry is the overlap tail of the flushed chunk
            carry_source = (carry + current)[-overlap:] if (carry + current) else ""
            current = sentence
            carry = carry_source

    # Flush remainder
    remainder = (carry + current).strip()
    if remainder:
        chunks.append(remainder)

    # Filter whitespace-only chunks and build result
    total = len(chunks)
    return [
        {
            "text": c,
            "chunk_index": i,
            "total_chunks": total,
            "source_file": source_file,
            "metadata": {**meta, "chunk_index": i, "total_chunks": total},
        }
        for i, c in enumerate(chunks)
        if c.strip()
    ]

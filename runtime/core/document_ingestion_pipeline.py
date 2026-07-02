"""Document Ingestion Pipeline — extract → chunk → store.

Wires document_extractor → document_chunker → VectorStore + KnowledgeStore.

Usage (async)::

    from core.document_ingestion_pipeline import ingest_document

    result = await ingest_document("/path/to/file.pdf", tenant_id="t_123")
    # Returns: { chunks_stored, topics, errors, file_type }

CLI::

    python3 runtime/core/document_ingestion_pipeline.py --file /path/to/file.pdf --tenant default
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Resolve repository root (two levels above runtime/core/)."""
    home = os.getenv("AI_HOME")
    if home:
        return Path(home)
    return Path(__file__).resolve().parents[2]


def _state_path() -> Path:
    from core.state_paths import tenant_state_dir
    p = tenant_state_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Topic extraction ───────────────────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "the a an and or but in on at to for of with from by is are was were be been "
    "have has had do does did will would could should may might shall can not no "
    "i you he she it we they this that these those as so if then when where which "
    "who whom what how all any both each few more most other some such than too "
    "very just also about into over after above below between through during before "
    "after".split()
)


def _extract_topics(text: str, n: int = 5) -> list[str]:
    """Extract n most-frequent meaningful words as topic labels."""
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    freq = Counter(w for w in words if w not in _STOP_WORDS)
    return [word for word, _ in freq.most_common(n)]


# ── Ingestion log ──────────────────────────────────────────────────────────────

def _append_ingestion_log(record: dict[str, Any]) -> None:
    log_path = _state_path() / "ingestion_log.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "document_ingested"}) + "\n")
    except Exception as e:
        logger.warning("Failed to write ingestion log: %s", e)


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def ingest_document(file_path: str, tenant_id: str | None = None) -> dict[str, Any]:
    """Extract text from file_path, chunk it, and store into vector + knowledge stores.

    Returns:
        { chunks_stored: int, topics: list, errors: list, file_type: str }
        or { needs_vision: True } for images
        or { error: str } on extraction failure
    """
    t_start = time.monotonic()
    errors: list[str] = []

    # 1. Extract
    try:
        from tools.document_extractor import extract  # noqa: PLC0415
        extracted = extract(file_path)
    except Exception as e:
        return {"error": f"Extractor import/call failed: {e}", "errors": [str(e)]}

    if "error" in extracted:
        return {"error": extracted["error"], "errors": [extracted["error"]]}

    # 2. Resolve text — vision_analyzer now handles images; fall back to filename if empty
    text: str = extracted.get("text") or ""
    if not text:
        text = Path(file_path).name
    file_type: str = extracted.get("file_type", "unknown")
    meta: dict = extracted.get("metadata") or {}

    # 3. Chunk
    try:
        from tools.document_chunker import chunk as chunk_text  # noqa: PLC0415
        chunks = chunk_text(text, source_file=file_path, metadata=meta)
    except Exception as e:
        errors.append(f"Chunker failed: {e}")
        chunks = []

    # 4. Store chunks in vector store
    chunks_stored = 0
    try:
        from memory.vector_store import get_vector_store  # noqa: PLC0415
        vs = get_vector_store()
        file_stem = Path(file_path).stem
        for c in chunks:
            key = f"doc_{file_stem}_{c['chunk_index']}"
            vs.store(
                key,
                c["text"],
                metadata={
                    "source_file": file_path,
                    "chunk_index": c["chunk_index"],
                    "total_chunks": c["total_chunks"],
                    "file_type": file_type,
                    "memory_type": "semantic",
                    **(c.get("metadata") or {}),
                },
                importance=0.6,
            )
            chunks_stored += 1
    except Exception as e:
        errors.append(f"VectorStore storage failed: {e}")
        logger.warning("VectorStore storage error: %s", e)

    # 5. Extract topics and push to knowledge store
    topics: list[str] = _extract_topics(text[:5000])
    summary = text[:500].strip()
    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        ks = get_knowledge_store()
        for topic in topics:
            ks.add_knowledge(topic, f"[{file_type}] {Path(file_path).name}: {summary}")
    except Exception as e:
        errors.append(f"KnowledgeStore update failed: {e}")
        logger.warning("KnowledgeStore error: %s", e)

    # 6. Write ingestion log
    duration_ms = int((time.monotonic() - t_start) * 1000)
    _append_ingestion_log({
        "file": file_path,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunks": chunks_stored,
        "topics": topics,
        "tenant_id": tenant_id or "default",
        "file_type": file_type,
        "duration_ms": duration_ms,
        "errors": errors,
    })

    return {
        "chunks_stored": chunks_stored,
        "topics": topics,
        "errors": errors,
        "file_type": file_type,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    # Ensure runtime/ is on sys.path for sibling imports
    _runtime = Path(__file__).resolve().parent.parent
    if str(_runtime) not in sys.path:
        sys.path.insert(0, str(_runtime))

    parser = argparse.ArgumentParser(description="Ingest a document into the AI-Employee knowledge base.")
    parser.add_argument("--file", required=True, help="Path to the file to ingest")
    parser.add_argument("--tenant", default="default", help="Tenant ID")
    args = parser.parse_args()

    result = asyncio.run(ingest_document(args.file, args.tenant))
    print(json.dumps(result))

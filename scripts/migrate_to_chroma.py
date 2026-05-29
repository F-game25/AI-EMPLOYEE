#!/usr/bin/env python3
"""Migrate state/*.json vector stores into Chroma. Idempotent (deterministic ids)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/lf/AI-EMPLOYEE/runtime")
from memory.memory_adapter import get_adapter  # noqa: E402

STATE = Path("/home/lf/AI-EMPLOYEE/state")


def chunk_text(text: str, size: int = 1000, overlap: int = 200):
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(1, size - overlap)
    return chunks or [text]


def main() -> int:
    adapter = get_adapter()
    print(f"Adapter status: {adapter.status()}")

    migrated = 0

    # 1) knowledge_store.json  (entries[] with id/topic/content/source/importance)
    p = STATE / "knowledge_store.json"
    if p.exists():
        with open(p) as f:
            d = json.load(f)
        for e in d.get("entries", []):
            content = (e.get("content") or "").strip()
            if not content:
                continue
            orig_id = e.get("id", f"auto{migrated}")
            for idx, chunk in enumerate(chunk_text(content)):
                meta = {
                    "source": e.get("source", "knowledge_store"),
                    "topic": e.get("topic", "general"),
                    "importance": float(e.get("importance", 0.5)),
                    "orig_id": orig_id,
                    "chunk_idx": idx,
                    "origin_store": "knowledge_store.json",
                }
                adapter.add(chunk, metadata=meta, id=f"k_{orig_id}_c{idx}")
                migrated += 1

    # 2) vector_store.json  (entries[] with key/text/metadata/importance)
    p = STATE / "vector_store.json"
    if p.exists():
        with open(p) as f:
            d = json.load(f)
        for e in d.get("entries", []):
            text = (e.get("text") or "").strip()
            if not text:
                continue
            key = e.get("key", f"auto{migrated}")
            meta = {
                **(e.get("metadata") or {}),
                "importance": float(e.get("importance", 0.5)),
                "origin_store": "vector_store.json",
            }
            adapter.add(text, metadata=meta, id=f"v_{key}")
            migrated += 1

    # 3) memory_index.json  (memories[] with id/text/importance)
    p = STATE / "memory_index.json"
    if p.exists():
        with open(p) as f:
            d = json.load(f)
        for e in d.get("memories", []):
            text = (e.get("text") or "").strip()
            if not text:
                continue
            mid = e.get("id", f"auto{migrated}")
            meta = {
                "importance": float(e.get("importance", 0.5)),
                "origin_store": "memory_index.json",
            }
            adapter.add(text, metadata=meta, id=f"m_{mid}")
            migrated += 1

    print(f"Migrated {migrated} entries into Chroma")
    print(f"Total count in Chroma: {adapter.count()}")

    # Backup originals (one-shot — won't overwrite an existing backup)
    for name in ("knowledge_store.json", "vector_store.json", "memory_index.json"):
        src = STATE / name
        if src.exists():
            bak = STATE / f"{name}.pre-chroma"
            if not bak.exists():
                bak.write_bytes(src.read_bytes())
                print(f"Backed up {name} -> {name}.pre-chroma")

    return 0


if __name__ == "__main__":
    sys.exit(main())

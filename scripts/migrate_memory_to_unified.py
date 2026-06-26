#!/usr/bin/env python3
"""Migrate legacy JSON memory stores into state/memory/unified_memory.json.

Dry-run is the default. Pass --apply to write canonical records.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from core.state_paths import canonical_state_dir  # noqa: E402
from memory.schema import MemoryRecord  # noqa: E402
from memory.unified_store import UnifiedMemoryStore  # noqa: E402


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, default=str).strip()


def _existing_ids(path: Path) -> set[str]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return set()
    records = raw.get("records") or []
    return {str(row.get("id")) for row in records if isinstance(row, dict) and row.get("id")}


def _knowledge_records(state: Path) -> list[MemoryRecord]:
    path = state / "knowledge_store.json"
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return []

    records: list[MemoryRecord] = []
    for entry in raw.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get("id") or entry.get("title") or len(records)).replace(" ", "_").lower()
        title = str(entry.get("title") or entry.get("topic") or eid)
        content = _text(entry.get("content") or entry.get("text") or "")
        if not content:
            continue
        records.append(MemoryRecord.create(
            f"{title}\n\n{content}".strip(),
            id=f"ks:{eid}",
            memory_type="knowledge_graph",
            source=entry.get("source", "knowledge_store"),
            topic=title,
            tags=entry.get("tags") or [],
            importance=entry.get("importance", 0.5),
            metadata={"origin_store": "knowledge_store.entries", "entry_id": eid},
        ))

    for topic, items in (raw.get("topics") or {}).items():
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            content = _text(item.get("content") or item)
            if not content:
                continue
            records.append(MemoryRecord.create(
                f"{topic}\n\n{content}".strip(),
                id=f"ks:topic:{topic}:{idx}",
                memory_type="knowledge_graph",
                source="knowledge_store",
                topic=str(topic),
                tags=[str(topic)],
                metadata={"origin_store": "knowledge_store.topics", "topic": topic},
            ))

    for idx, item in enumerate(raw.get("insights", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "insight")
        content = _text(item.get("content") or item)
        if not content:
            continue
        records.append(MemoryRecord.create(
            f"{topic}\n\n{content}".strip(),
            id=str(item.get("id") or f"ks:insight:{topic}:{idx}"),
            memory_type="knowledge_graph",
            source="knowledge_store",
            topic=topic,
            tags=[topic],
            metadata={"origin_store": "knowledge_store.insights", "topic": topic},
        ))
    return records


def _memory_index_records(state: Path) -> list[MemoryRecord]:
    raw = _load_json(state / "memory_index.json")
    if not isinstance(raw, dict):
        return []
    records: list[MemoryRecord] = []
    for idx, item in enumerate(raw.get("memories", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text") or "")
        if not text:
            continue
        records.append(MemoryRecord.create(
            text,
            id=str(item.get("id") or f"mi:{idx}"),
            memory_type="long_term",
            source="memory_index",
            importance=item.get("importance", 0.5),
            metadata={
                "origin_store": "memory_index",
                "usage_count": item.get("usage_count", 0),
                "last_used": item.get("last_used"),
            },
        ))
    return records


def _vector_records(state: Path) -> list[MemoryRecord]:
    raw = _load_json(state / "vector_store.json")
    if not isinstance(raw, dict):
        return []
    records: list[MemoryRecord] = []
    for idx, item in enumerate(raw.get("entries", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text") or "")
        if not text:
            continue
        metadata = dict(item.get("metadata") or {})
        records.append(MemoryRecord.create(
            text,
            id=str(item.get("key") or f"vector:{idx}"),
            memory_type=metadata.get("memory_type", "semantic"),
            source=metadata.get("source", "vector_store"),
            importance=item.get("importance", 0.5),
            agent=metadata.get("agent"),
            project_id=metadata.get("project_id") or None,
            session_id=metadata.get("session_id") or None,
            task_id=metadata.get("task_id") or None,
            tags=metadata.get("tags") or [],
            metadata={**metadata, "origin_store": "vector_store"},
        ))
    return records


def _json_memory_records(state: Path) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    for memory_type in ("preference", "tool_history", "project"):
        raw = _load_json(state / f"memory_{memory_type}.json")
        if not isinstance(raw, dict):
            continue
        for mid, item in raw.items():
            if not isinstance(item, dict):
                continue
            text = _text(item.get("content") or item.get("text") or "")
            if not text:
                continue
            metadata = dict(item.get("metadata") or {})
            records.append(MemoryRecord.create(
                text,
                id=str(item.get("id") or mid),
                memory_type=memory_type,
                source=metadata.get("source", f"memory_{memory_type}"),
                importance=metadata.get("importance", 0.5),
                tags=metadata.get("tags") or [],
                metadata={**metadata, "origin_store": f"memory_{memory_type}.json"},
            ))
    return records


def collect_records(state: Path) -> list[MemoryRecord]:
    records: dict[str, MemoryRecord] = {}
    for record in [
        *_knowledge_records(state),
        *_memory_index_records(state),
        *_vector_records(state),
        *_json_memory_records(state),
    ]:
        records[record.id] = record
    return list(records.values())


def run(*, state: Path, apply: bool = False) -> dict[str, int | str]:
    unified_path = state / "memory" / "unified_memory.json"
    existing = _existing_ids(unified_path)
    records = collect_records(state)
    pending = [record for record in records if record.id not in existing]

    if apply:
        store = UnifiedMemoryStore(path=unified_path)
        for record in pending:
            store.upsert(record)

    return {
        "state": str(state),
        "found": len(records),
        "existing": len(existing),
        "pending": len(pending),
        "written": len(pending) if apply else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write records; default is dry-run")
    parser.add_argument("--state-dir", default=str(canonical_state_dir()), help="state directory to read")
    args = parser.parse_args()

    summary = run(state=Path(args.state_dir).resolve(), apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"{mode} unified memory migration")
    for key in ("state", "found", "existing", "pending", "written"):
        print(f"{key}: {summary[key]}")
    if not args.apply:
        print("Re-run with --apply to write pending records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

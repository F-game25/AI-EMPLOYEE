from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
if str(REPO / "runtime") not in sys.path:
    sys.path.insert(0, str(REPO / "runtime"))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from migrate_memory_to_unified import run  # noqa: E402
from memory.unified_store import UnifiedMemoryStore  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_migration_dry_run_does_not_create_unified_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    _write_json(tmp_path / "memory_index.json", {
        "memories": [{"id": "m1", "text": "dry run memory", "importance": 0.8}]
    })

    summary = run(state=tmp_path, apply=False)

    assert summary["found"] == 1
    assert summary["pending"] == 1
    assert summary["written"] == 0
    assert not (tmp_path / "memory" / "unified_memory.json").exists()


def test_migration_writes_legacy_sources_to_unified_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    _write_json(tmp_path / "knowledge_store.json", {
        "entries": [{
            "id": "k1",
            "title": "Pricing",
            "content": "Annual plans convert better",
            "tags": ["pricing"],
        }],
        "topics": {"sales": [{"content": "Lead quality beats lead volume"}]},
    })
    _write_json(tmp_path / "memory_index.json", {
        "memories": [{"id": "m1", "text": "Planner should reuse sales context", "importance": 0.7}]
    })
    _write_json(tmp_path / "vector_store.json", {
        "entries": [{
            "key": "v1",
            "text": "Semantic vector memory",
            "metadata": {"memory_type": "semantic", "source": "vector"},
            "importance": 0.6,
        }]
    })
    _write_json(tmp_path / "memory_preference.json", {
        "pref1": {"content": "Keep dashboard panels compact", "metadata": {"tags": ["ui"]}}
    })

    summary = run(state=tmp_path, apply=True)

    assert summary["found"] == 5
    assert summary["written"] == 5

    store = UnifiedMemoryStore(path=tmp_path / "memory" / "unified_memory.json")
    assert store.get("ks:k1") is not None
    assert store.get("ks:topic:sales:1") is not None
    assert store.get("m1") is not None
    assert store.get("v1") is not None
    pref = store.get("pref1")
    assert pref is not None
    assert pref.memory_type == "preference"


def test_migration_skips_existing_canonical_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    _write_json(tmp_path / "memory_index.json", {
        "memories": [{"id": "m1", "text": "existing memory", "importance": 0.7}]
    })

    first = run(state=tmp_path, apply=True)
    second = run(state=tmp_path, apply=True)

    assert first["written"] == 1
    assert second["written"] == 0

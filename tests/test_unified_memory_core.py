from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


@pytest.fixture()
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setenv("STATE_DIR", str(state))
    monkeypatch.setenv("TENANT_ID", "tenant-a")
    return state


def _service(state: Path):
    from memory.service import MemoryService
    from memory.short_term_cache import ShortTermCache
    from memory.strategy_store import StrategyStore
    from memory.unified_store import UnifiedMemoryStore
    from memory.vector_store import VectorStore

    return MemoryService(
        store=UnifiedMemoryStore(path=state / "memory" / "unified_memory.json"),
        vector_store=VectorStore(),
        cache=ShortTermCache(),
        strategy_store=StrategyStore(path=state / "strategies.json"),
    )


def test_memory_record_normalizes_labels_and_scores() -> None:
    from memory.schema import MemoryRecord

    record = MemoryRecord.create(
        "Persistent pricing rule",
        id="mem-1",
        tenant_id="tenant-a",
        memory_type="UNKNOWN",
        project_id="project-7",
        tags=["Pricing", "pricing", " Money "],
        confidence=2,
        importance=-1,
        visibility="external",
    )

    assert record.memory_type == "semantic"
    assert record.scope == "project"
    assert record.tags == ["pricing", "money"]
    assert record.confidence == 1.0
    assert record.importance == 0.0
    assert record.visibility == "private"


def test_unified_store_persists_and_filters(isolated_state: Path) -> None:
    from memory.schema import MemoryRecord
    from memory.unified_store import UnifiedMemoryStore

    path = isolated_state / "memory" / "unified_memory.json"
    store = UnifiedMemoryStore(path=path)
    store.upsert(
        MemoryRecord.create(
            "Client Alpha prefers weekly invoices",
            id="alpha-pref",
            tenant_id="tenant-a",
            memory_type="preference",
            project_id="alpha",
            tags=["billing"],
            importance=0.8,
        )
    )
    store.upsert(
        MemoryRecord.create(
            "Client Beta uses monthly reports",
            id="beta-pref",
            tenant_id="tenant-b",
            memory_type="preference",
            project_id="beta",
            tags=["reporting"],
        )
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["count"] == 2

    results = store.search(
        query="weekly invoices",
        tenant_id="tenant-a",
        memory_type="preference",
        project_id="alpha",
        tags=["billing"],
    )
    assert [r.id for r in results] == ["alpha-pref"]
    assert store.get("alpha-pref") is not None


def test_memory_service_writes_canonical_cache_and_vector(isolated_state: Path) -> None:
    service = _service(isolated_state)

    routed = service.remember(
        "Semantic memory about enterprise renewal pricing",
        key="pricing-rule",
        memory_type="semantic",
        source="test",
        project_id="enterprise",
        tags=["pricing"],
        importance=0.9,
    )

    assert routed["id"] == "pricing-rule"
    assert routed["vector_stored"] is True

    retrieved = service.retrieve("renewal pricing", project_id="enterprise", tags=["pricing"], top_k=3)
    assert retrieved
    assert retrieved[0]["id"] == "pricing-rule"
    assert retrieved[0]["metadata"]["project_id"] == "enterprise"

    canonical_path = isolated_state / "memory" / "unified_memory.json"
    assert canonical_path.exists()


def test_memory_router_legacy_api_uses_canonical_store(isolated_state: Path) -> None:
    from memory.memory_router import MemoryRouter
    from memory.short_term_cache import ShortTermCache
    from memory.strategy_store import StrategyStore
    from memory.vector_store import VectorStore

    router = MemoryRouter(
        vector_store=VectorStore(),
        cache=ShortTermCache(),
        strategy_store=StrategyStore(path=isolated_state / "strategies.json"),
    )

    stored = router.store(
        "ops-note",
        "Ops agent should retry locked files once before failing",
        memory_type="procedural",
        source="pytest",
        importance=0.9,
        extra={"project_id": "ops"},
    )
    assert stored["cache_key"] == "ops-note"
    assert stored["vector_stored"] is True

    exact = router.get("ops-note")
    assert exact is not None
    assert exact["id"] == "ops-note"

    results = router.retrieve("retry locked files", memory_type="procedural")
    assert any(row["id"] == "ops-note" for row in results)

    stats = router.stats()
    assert stats["canonical_count"] == 1


def test_record_outcome_records_strategy_and_success_memory(isolated_state: Path) -> None:
    service = _service(isolated_state)

    routed = service.record_outcome(
        action="research_agent",
        success=True,
        context="validated vendor pricing source",
        result={"source": "vendor"},
        goal_type="research",
    )

    assert routed["strategy_recorded"] is True
    assert routed["memory_stored"] is True

    retrieved = service.retrieve("validated vendor pricing", memory_type="episodic", top_k=5)
    assert any(row["metadata"].get("action") == "research_agent" for row in retrieved)

    strategies = json.loads((isolated_state / "strategies.json").read_text(encoding="utf-8"))
    assert strategies[0]["agent"] == "research_agent"

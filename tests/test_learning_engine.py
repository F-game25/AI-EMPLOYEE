from __future__ import annotations

import importlib
import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _reload(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_learning_engine_updates_strategy_agent_and_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    le = _reload("core.learning_engine")
    engine = le.get_learning_engine()

    engine.add_conversation_message(role="user", message="I run an ecommerce clothing business.")
    update = engine.record_task(
        task_input="find leads for ecommerce clothing business",
        chosen_agent="lead_hunter",
        strategy_used="lead_generation:lead_hunter",
        result={"status": "success"},
        success_score=1.0,
        decision_reason="Selected lead_hunter because...",
        memories_used=[{"id": "m1", "text": "fashion brands rely heavily on Instagram + influencers"}],
    )

    assert update["reward"] == 1.0
    assert update["strategy"]["use_count"] == 1
    assert update["agent"]["use_count"] == 1
    assert (tmp_path / "state" / "learning_engine.json").exists()

    found = engine.search_memory("ecommerce clothing leads", top_k=3)
    assert isinstance(found.get("episodic"), list)
    assert len(found["episodic"]) >= 1
    assert isinstance(found.get("short_term"), list)
    assert len(found["short_term"]) >= 1


def test_learning_engine_short_term_memory_is_limited(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    le = _reload("core.learning_engine")
    engine = le.get_learning_engine()
    for i in range(30):
        engine.add_conversation_message(role="user", message=f"message-{i}")
    metrics = engine.metrics()
    assert metrics["memory_sizes"]["short_term"] == 20

from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core.brain_model import select_agent


def test_confidence_routes_to_orchestrator_when_low():
    features = {
        "lead_hunter": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
        "email_ninja": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
        "intel_agent": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
        "social_guru": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
        "data_analyst": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
        "task_orchestrator": {"task_match": 0.01, "success_rate": 0.01, "speed": 0.01, "complexity": 0.01},
    }
    selected, confidence, _ = select_agent(features)
    assert selected == "task_orchestrator"
    assert confidence < 0.4

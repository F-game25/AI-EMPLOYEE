from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from neural_brain.graph.graph_to_dashboard import graph_to_dashboard
from neural_brain.utils.shape_validators import validate_dashboard_graph


def test_graph_to_dashboard_returns_canonical_links_and_valid_groups():
    payload = graph_to_dashboard(
        {
            "nodes": [
                {"id": "a", "label": "Strategy A", "labels": ["Strategy"], "props": {}},
                {"id": "b", "label": "Memory B", "labels": ["Memory"], "props": {}},
                {"id": "c", "label": "Agent C", "labels": ["Agent"], "props": {}},
            ],
            "links": [
                {"source": "a", "target": "b", "rel": "RELATES_TO", "props": {"weight": 0.7}},
                {"source": "b", "target": "c", "rel": "USED_IN", "props": {}},
            ],
        }
    )

    assert set(payload) >= {"nodes", "links", "connections", "stats"}
    assert payload["links"] == [
        {"source": "a", "target": "b", "strength": 0.7},
        {"source": "b", "target": "c", "strength": 0.5},
    ]
    assert payload["connections"] == [
        {"from": "a", "to": "b", "weight": 0.7},
        {"from": "b", "to": "c", "weight": 0.5},
    ]
    assert [node["type"] for node in payload["nodes"]] == ["strategy", "memory", "agent"]
    assert [node["group"] for node in payload["nodes"]] == ["money", "memory", "agent"]
    assert validate_dashboard_graph(payload) == (True, [])


def test_dashboard_graph_validator_rejects_links_to_missing_nodes():
    valid, errors = validate_dashboard_graph(
        {
            "nodes": [{"id": "a", "label": "A", "type": "skill", "group": "money"}],
            "links": [{"source": "a", "target": "missing", "strength": 0.4}],
        }
    )

    assert valid is False
    assert any("unknown node" in error for error in errors)

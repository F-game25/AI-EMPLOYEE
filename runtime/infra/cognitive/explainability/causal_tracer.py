import json
import os
import logging
from pathlib import Path
from .schema import CausalChain
import time

logger = logging.getLogger(__name__)
_BUS_LOG = Path(os.path.expanduser("~/.ai-employee")) / "state" / "bus.jsonl"
_MAX_DEPTH = 20


def trace(root_event_id: str, tenant_id: str) -> CausalChain:
    events = _load_events()
    chain = []
    visited = set()
    queue = [root_event_id]
    depth = 0
    while queue and depth < _MAX_DEPTH:
        eid = queue.pop(0)
        if eid in visited:
            continue
        visited.add(eid)
        for ev in events:
            if ev.get("id") == eid:
                chain.append(ev)
                caused = ev.get("caused_by")
                if caused and caused not in visited:
                    queue.append(caused)
        depth += 1
    chain.sort(key=lambda x: x.get("timestamp", 0))
    return CausalChain(root_event_id=root_event_id, tenant_id=tenant_id, chain=chain)


def _load_events() -> list[dict]:
    events = []
    try:
        bus_path = _BUS_LOG
        if not bus_path.exists():
            # Also try state/ relative to project
            alt = Path(os.path.expanduser("~")) / "AI-EMPLOYEE" / "state" / "bus.jsonl"
            if alt.exists():
                bus_path = alt
        if bus_path.exists():
            with open(bus_path) as f:
                for line in f:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("Could not load bus log: %s", e)
    return events[-5000:]  # last 5000 events


_instance = None


def get_causal_tracer():
    global _instance
    if _instance is None:
        _instance = type("CausalTracer", (), {"trace": staticmethod(trace)})()
    return _instance

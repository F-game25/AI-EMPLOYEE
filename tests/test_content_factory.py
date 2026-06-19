"""M5 Content Factory — real artifacts + approval-gated publish queue (never auto-posts)."""
import os
import sys
import tempfile
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _fresh(monkeypatch):
    monkeypatch.setenv("STATE_DIR", tempfile.mkdtemp())
    import importlib
    import content.publish_queue as pq
    import content.content_factory as cf
    importlib.reload(pq)
    importlib.reload(cf)
    return cf, pq


def test_produce_generates_artifacts_and_queues_pending(monkeypatch):
    cf, _pq = _fresh(monkeypatch)
    out = cf.get_content_factory().produce({"topic": "ai pricing", "platforms": ["blog"]})
    assert out["ok"] is True
    assert len(out["queued"]) == 1
    # everything is staged pending_approval — nothing auto-published
    assert all(q["status"] == "pending_approval" for q in out["queued"])
    # honest artifact data present
    assert "artifacts" in out and len(out["artifacts"]) == 1


def test_batch_variants(monkeypatch):
    cf, _pq = _fresh(monkeypatch)
    out = cf.get_content_factory().batch("launch announcement", variants=3, platform="twitter")
    assert out["ok"] is True
    assert len(out["queued"]) == 3
    assert all(q["platform"] == "twitter" for q in out["queued"])


def test_empty_topic_is_honest_error(monkeypatch):
    cf, _pq = _fresh(monkeypatch)
    assert cf.get_content_factory().produce({"topic": ""})["ok"] is False


def test_queue_never_auto_publishes_approval_required(monkeypatch):
    cf, pq = _fresh(monkeypatch)
    out = cf.get_content_factory().produce({"topic": "x", "platforms": ["blog"]})
    eid = out["queued"][0]["id"]
    q = pq.get_publish_queue()
    # approve() routes through the HITL gate; status only becomes 'approved' (ready),
    # which is NOT an actual post — there is no autonomous publish anywhere.
    res = q.approve(eid)
    assert res["ok"] is True
    assert res["status"] in ("approved", "pending_approval")
    # list reflects the queue; nothing is ever 'published' autonomously
    statuses = {i["status"] for i in q.list()}
    assert "published" not in statuses


def test_reject_marks_rejected(monkeypatch):
    cf, pq = _fresh(monkeypatch)
    out = cf.get_content_factory().produce({"topic": "x"})
    eid = out["queued"][0]["id"]
    assert pq.get_publish_queue().reject(eid)["status"] == "rejected"


def test_broker_capability_registered_and_runs(monkeypatch):
    _fresh(monkeypatch)
    from companion.capability_registry import get_capability_registry
    from companion.execution_broker import get_execution_broker
    reg = get_capability_registry()
    cap = reg.get("content.produce")
    assert cap is not None and cap.risk_level == "L1"
    out = get_execution_broker()._exec_content_produce(cap, {"topic": "ai pricing", "platforms": ["blog"]})
    assert out["status"] == "ok"
    assert len(out["queued"]) == 1

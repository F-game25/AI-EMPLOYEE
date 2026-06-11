"""Tests for the Context Database Layer (runtime/memory/context_db/).

Deterministic + isolated: every test runs against a tmp CONTEXT_DB_DIR so
the real ~/.ai-employee state is never touched. No network, no LLM (the
compressor's LLM polish stays off; the retriever's vector lane is exercised
both available and force-disabled).
"""
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import pytest  # noqa: E402

from memory.context_db import context_permissions as perms  # noqa: E402
from memory.context_db.context_loader import load  # noqa: E402
from memory.context_db.context_tree import ContextTree  # noqa: E402
from memory.context_db.recursive_retriever import retrieve  # noqa: E402
from memory.context_db.session_compressor import compress_session  # noqa: E402

from companion.execution_broker import ExecutionBroker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_context_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_DB_DIR", str(tmp_path / "context_db"))
    monkeypatch.delenv("CONTEXT_DB_LLM_COMPRESS", raising=False)
    monkeypatch.delenv("CONTEXT_DB_VECTOR", raising=False)
    yield


def _seed_tree() -> ContextTree:
    tree = ContextTree()
    tree.ensure_layout()
    tree.write("/project/goals/q3-revenue",
               "Q3 goal: reach 10k MRR through outbound sales and the CRM pipeline.")
    tree.write("/project/decisions/db-choice",
               "We decided to use PostgreSQL as the primary database for deals.")
    tree.write("/project/tasks/onboarding-flow",
               "Build the tenant onboarding flow with JWT registration.")
    tree.write("/project/code/retriever-notes",
               "The recursive retriever fuses BM25 and vector ranks with RRF.")
    tree.write("/project/reports/june-summary",
               "June report: uptime 99.9 percent, research budget consumed 40 percent.")
    tree.write("/user/preferences/reply-style",
               "User prefers short bullet-point replies in Dutch.")
    return tree


# ── ContextTree ───────────────────────────────────────────────────────────────

def test_tree_write_read_list_delete_roundtrip():
    tree = ContextTree()
    node_id = tree.write("/project/goals/launch", "Launch the beta in July. " * 4,
                         metadata={"owner": "lars"})
    assert isinstance(node_id, str) and len(node_id) == 16

    node = tree.read("/project/goals/launch")
    assert node is not None
    assert node["id"] == node_id
    assert node["path"] == "/project/goals/launch"
    assert node["metadata"]["owner"] == "lars"
    assert node["created_at"] and node["updated_at"]

    listing = tree.list("/project/goals")
    assert any(e["kind"] == "node" and e["path"] == "/project/goals/launch"
               for e in listing)

    assert tree.delete("/project/goals/launch") is True
    assert tree.read("/project/goals/launch") is None
    assert tree.delete("/project/goals/launch") is False


def test_tree_stable_id_survives_rewrite():
    tree = ContextTree()
    first = tree.write("/project/tasks/t1", "version one")
    second = tree.write("/project/tasks/t1", "version two — totally new content")
    assert first == second  # id derives from tenant:path, not content


def test_tree_path_traversal_refused():
    tree = ContextTree()
    for bad in ("../../etc/passwd", "/project/../../etc", "/etc/passwd",
                "/project/goals/../../..", ""):
        with pytest.raises(ValueError):
            tree.write(bad, "evil")
    assert tree.read("../../etc/passwd") is None
    assert tree.delete("../../etc/passwd") is False


def test_tree_summary_auto_generated():
    tree = ContextTree()
    long_text = ("The first sentence carries the gist. " +
                 "Padding sentence here. " * 40)
    tree.write("/project/reports/long", long_text)
    node = tree.read("/project/reports/long")
    assert node["summary"]
    assert len(node["summary"]) <= 210
    assert node["summary"].startswith("The first sentence")


def test_tree_move_keeps_created_at_and_rederives_id():
    tree = ContextTree()
    tree.write("/project/tasks/old-name", "task body")
    original = tree.read("/project/tasks/old-name")
    moved = tree.move("/project/tasks/old-name", "/project/tasks/new-name")
    assert moved["path"] == "/project/tasks/new-name"
    assert moved["created_at"] == original["created_at"]
    assert moved["id"] != original["id"]
    assert tree.read("/project/tasks/old-name") is None
    assert tree.read("/project/tasks/new-name") is not None


# ── Permissions ───────────────────────────────────────────────────────────────

def test_permissions_fail_closed():
    assert perms.check("/project/goals/x", "default", None) is True
    assert perms.check("/project/goals/x", "default", ["/project/goals"]) is True
    assert perms.check("/project/code/x", "default", ["/project/goals"]) is False
    assert perms.check("/project/goals/x", "default", []) is False        # empty allowlist
    assert perms.check("../../etc", "default", None) is False             # traversal
    assert perms.check("/project/goals/x", "bad tenant!", None) is False  # bad tenant
    assert perms.check(None, "default", None) is False


# ── Loader (L0/L1/L2 + budget) ────────────────────────────────────────────────

def test_loader_levels_return_increasing_detail():
    tree = ContextTree()
    content = "Alpha beta gamma. " * 200  # > L1 preview size
    tree.write("/project/code/big", content, metadata={"lang": "py"})

    l0 = load(["/project/code/big"], level="L0", tree=tree)
    l1 = load(["/project/code/big"], level="L1", tree=tree)
    l2 = load(["/project/code/big"], level="L2", tree=tree)

    v0, v1, v2 = l0["views"][0], l1["views"][0], l2["views"][0]
    assert "content" not in v0 and "content_preview" not in v0
    assert len(v1["content_preview"]) == 1500 and "content" not in v1
    assert v1["metadata"] == {"lang": "py"}
    assert len(v2["content"]) == len(content)
    assert l0["chars_used"] < l1["chars_used"] < l2["chars_used"]
    for res in (l0, l1, l2):
        assert res["truncated"] is False


def test_loader_token_budget_truncates():
    tree = ContextTree()
    for i in range(4):
        tree.write(f"/project/reports/r{i}", "word " * 500)  # 2500 chars each
    items = [f"/project/reports/r{i}" for i in range(4)]
    out = load(items, level="L2", max_chars=3000, tree=tree)
    assert out["truncated"] is True
    assert 0 < len(out["views"]) < 4
    assert out["chars_used"] <= 3000


def test_loader_reports_missing_nodes():
    out = load(["/project/goals/ghost"], level="L0", tree=ContextTree())
    assert out["views"] == []
    assert out["missing"] == ["/project/goals/ghost"]


# ── Recursive retriever ───────────────────────────────────────────────────────

def test_retriever_finds_relevant_node_with_trace():
    tree = _seed_tree()
    out = retrieve("which database did we decide to use", tree=tree)
    assert out["nodes"], "expected at least one result"
    assert out["nodes"][0]["path"] == "/project/decisions/db-choice"
    # Trace is the OpenViking signature — always present and structured.
    assert out["trace"], "trace must never be empty"
    actions = [t["action"] for t in out["trace"]]
    assert "scope_filter" in actions
    assert "bm25_rank" in actions
    assert "rrf_fuse" in actions
    for step in out["trace"]:
        assert {"step", "action", "reason"} <= set(step)


def test_retriever_scope_filter_excludes_disallowed_paths():
    tree = _seed_tree()
    out = retrieve("which database did we decide to use", tree=tree,
                   filters={"tenant": "default",
                            "allowed_scopes": ["/project/goals"]})
    paths = [n["path"] for n in out["nodes"]]
    assert all(p.startswith("/project/goals") for p in paths)
    assert "/project/decisions/db-choice" not in paths
    scope_steps = [t for t in out["trace"] if t["action"] == "scope_filter"]
    assert scope_steps and scope_steps[0]["chosen"] < scope_steps[0]["candidates_considered"]


def test_retriever_bm25_only_when_vector_unavailable(monkeypatch):
    monkeypatch.setenv("CONTEXT_DB_VECTOR", "0")
    tree = _seed_tree()
    out = retrieve("recursive retriever BM25 fusion", tree=tree)
    assert out["nodes"]
    assert out["nodes"][0]["path"] == "/project/code/retriever-notes"
    assert any(t["action"] == "vector_unavailable" for t in out["trace"])
    assert not any(t["action"] == "vector_rank" for t in out["trace"])


def test_retriever_levels_set_view_richness():
    tree = _seed_tree()
    out = retrieve("sales pipeline onboarding retriever report replies goal",
                   levels=("L0", "L1"), tree=tree, top_k=6)
    assert out["nodes"]
    assert out["nodes"][0]["level"] == "L1"  # top results get the richer tier
    if len(out["nodes"]) > 3:
        assert out["nodes"][-1]["level"] == "L0"


def test_retriever_never_throws_on_garbage():
    out = retrieve("", tree=ContextTree())
    assert out["nodes"] == [] and out["trace"]
    out2 = retrieve("anything", filters={"allowed_scopes": "not-a-list"},
                    tree=_seed_tree())
    assert out2["nodes"] == []  # malformed allowlist fails closed
    assert out2["trace"]


# ── Session compressor ────────────────────────────────────────────────────────

def test_compressor_extracts_decision_and_preference():
    tree = ContextTree()
    messages = [
        {"role": "user", "content": "Hoi, even over het project."},
        {"role": "assistant",
         "content": "We decided to use PostgreSQL for deal storage. "
                    "It handles the pipeline volume."},
        {"role": "user", "content": "Good. I prefer short bullet-point replies."},
        {"role": "assistant", "content": "Noted. Anything else?"},
    ]
    out = compress_session(messages, project_id="alpha", tree=tree)
    assert out["written_nodes"]
    decision_nodes = [p for p in out["written_nodes"]
                      if p.startswith("/project/alpha/decisions/")]
    memory_nodes = [p for p in out["written_nodes"]
                    if p.startswith("/project/alpha/memory/")]
    assert decision_nodes and memory_nodes
    stored = tree.read(decision_nodes[0])
    assert "PostgreSQL" in stored["content"]  # verbatim, not fabricated
    assert stored["metadata"]["kind"] == "decision"
    pref = tree.read(memory_nodes[0])
    assert "bullet-point" in pref["content"]


def test_compressor_invents_nothing_from_empty_or_smalltalk():
    tree = ContextTree()
    assert compress_session([], tree=tree)["written_nodes"] == []
    smalltalk = [{"role": "user", "content": "hi"},
                 {"role": "assistant", "content": "hello, how can I help?"}]
    assert compress_session(smalltalk, tree=tree)["written_nodes"] == []
    assert compress_session("not-a-list", tree=tree)["written_nodes"] == []


# ── Broker integration ────────────────────────────────────────────────────────

def test_broker_context_retrieve_returns_structured_result():
    _seed_tree()
    out = ExecutionBroker._exec_context_retrieve(
        None, {"query": "which database did we decide to use"})
    assert out["status"] == "ok"
    assert isinstance(out["nodes"], list) and isinstance(out["trace"], list)
    assert out["nodes"][0]["path"] == "/project/decisions/db-choice"


def test_broker_context_executors_never_throw_on_garbage():
    assert ExecutionBroker._exec_context_retrieve(None, {})["status"] == "error"
    assert ExecutionBroker._exec_context_retrieve(
        None, {"query": "x", "filters": "garbage", "top_k": "9"})["status"] == "ok"
    assert ExecutionBroker._exec_context_write(None, {})["status"] == "error"
    refused = ExecutionBroker._exec_context_write(
        None, {"path": "../../etc/passwd", "content": "evil"})
    assert refused["status"] == "refused"
    assert ExecutionBroker._exec_context_compress_session(
        None, {"messages": "nope"})["status"] == "error"


def test_broker_context_write_then_retrieve_through_dispatch():
    wrote = ExecutionBroker._exec_context_write(
        None, {"path": "/project/decisions/test-broker",
               "content": "We decided the broker writes context nodes."})
    assert wrote["status"] == "ok" and wrote["node_id"]
    broker = ExecutionBroker()
    assert "context.retrieve" in broker._dispatch
    assert "context.write" in broker._dispatch
    assert "context.compress_session" in broker._dispatch
    routed = broker.execute(
        {"mode": "ask", "task_type": "context"},
        {"resolved_text": "retrieve context about the broker decision"},
        {"query": "broker decision context"},
        only_subsystems={"context"},
    )
    assert isinstance(routed, dict)
    assert "results" in routed and "approvals_required" in routed
    # context.retrieve is L0 → must be executable without approval.
    assert all(r.get("status") in ("ok", "error") for r in routed["results"])

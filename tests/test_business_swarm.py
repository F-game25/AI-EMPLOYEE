"""Tests for the Business Swarm Layer (Module 7). Offline-deterministic — no live LLM."""

import json
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from agents.business_swarm import agent_contracts as ac  # noqa: E402
from agents.business_swarm import task_decomposer  # noqa: E402
from agents.business_swarm.assignment_engine import assign  # noqa: E402
from agents.business_swarm.capability_profiles import build_contracts  # noqa: E402
from agents.business_swarm.dependency_manager import (  # noqa: E402
    DependencyCycleError,
    independent_groups,
    topological_order,
)
from agents.business_swarm.parallel_executor import run as execute_run  # noqa: E402
from agents.business_swarm.registry import BusinessSwarmRegistry  # noqa: E402
from agents.business_swarm.result_aggregator import aggregate  # noqa: E402
from agents.business_swarm.swarm import BusinessSwarm, get_business_swarm  # noqa: E402

_CATALOG = (
    Path(__file__).resolve().parents[1] / "runtime" / "config" / "agent_capabilities.json"
)

# Categories whose agents perform consequential external actions → must be gated.
_CONSEQUENTIAL_CATEGORIES = {
    "sales", "social", "content", "marketing", "growth", "ecommerce",
    "trading", "crypto", "intelligence", "communication",
}


def _catalog_agents():
    with open(_CATALOG, "r", encoding="utf-8") as fh:
        return json.load(fh).get("agents", {})


# ── Contracts derived from the REAL catalog ───────────────────────────────────

def test_contract_for_every_catalog_agent():
    contracts = build_contracts()
    catalog = _catalog_agents()
    assert set(contracts.keys()) == set(catalog.keys())
    assert len(contracts) >= 59


def test_every_contract_has_role_and_valid_risk():
    for c in build_contracts().values():
        assert isinstance(c.role, str) and c.role.strip(), f"{c.id} empty role"
        assert c.risk_level in ac.ALL_RISK_LEVELS, f"{c.id} bad risk {c.risk_level}"
        assert c.output_contract in ac.OUTPUT_CONTRACTS, f"{c.id} bad output {c.output_contract}"
        assert c.tools_allowed, f"{c.id} no tools"
        assert c.memory_scope, f"{c.id} no memory scope"
        assert c.success_metrics, f"{c.id} no metrics"


def test_consequential_agents_require_approval():
    catalog = _catalog_agents()
    contracts = build_contracts()
    for agent_id, meta in catalog.items():
        if str(meta.get("category", "")).lower() in _CONSEQUENTIAL_CATEGORIES:
            c = contracts[agent_id]
            assert c.requires_approval_for, f"{agent_id} consequential but no approval gate"
            assert c.risk_level in (ac.RISK_L2, ac.RISK_L3, ac.RISK_L4)


def test_analyst_agents_are_low_risk():
    contracts = build_contracts()
    catalog = _catalog_agents()
    for agent_id, meta in catalog.items():
        if str(meta.get("category", "")).lower() in {"analytics", "research", "strategy"}:
            # Analysts default low-risk unless they carry an explicit action keyword.
            c = contracts[agent_id]
            if not c.requires_approval_for:
                assert c.risk_level in (ac.RISK_L0, ac.RISK_L1)


def test_contract_to_from_dict_roundtrip():
    c = next(iter(build_contracts().values()))
    rebuilt = ac.AgentContract.from_dict(c.to_dict())
    assert rebuilt.to_dict() == c.to_dict()


# ── Decomposition ─────────────────────────────────────────────────────────────

def test_decompose_returns_3_to_8_subtasks():
    subtasks = task_decomposer.decompose("Launch a SaaS product for small accounting firms")
    assert 3 <= len(subtasks) <= 8
    for st in subtasks:
        assert st["id"] and st["description"] and st["needed_capability"]
        assert isinstance(st["depends_on"], list)


def test_decompose_handles_empty_goal():
    subtasks = task_decomposer.decompose("")
    assert 3 <= len(subtasks) <= 8


# ── Dependency ordering ───────────────────────────────────────────────────────

def test_topological_order_respects_dependencies():
    subtasks = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": ["a"]},
        {"id": "c", "depends_on": ["b"]},
    ]
    order = topological_order(subtasks)
    assert order.index("a") < order.index("b") < order.index("c")
    waves = independent_groups(subtasks)
    assert waves == [["a"], ["b"], ["c"]]


def test_cycle_is_detected():
    subtasks = [
        {"id": "a", "depends_on": ["b"]},
        {"id": "b", "depends_on": ["a"]},
    ]
    try:
        topological_order(subtasks)
        assert False, "expected DependencyCycleError"
    except DependencyCycleError:
        pass


# ── Assignment ────────────────────────────────────────────────────────────────

def test_assign_maps_to_real_catalog_ids():
    reg = BusinessSwarmRegistry()
    catalog_ids = set(_catalog_agents().keys())
    subtasks = task_decomposer.decompose("Run a B2B cold outreach campaign and analyze results")
    assignments = assign(subtasks, reg)
    assert len(assignments) == len(subtasks)
    matched = [a for a in assignments if a["agent_id"]]
    assert matched, "no subtask matched any agent"
    for a in matched:
        assert a["agent_id"] in catalog_ids
        assert a["contract"] is not None


# ── End-to-end run_goal ───────────────────────────────────────────────────────

def test_run_goal_returns_structured_aggregate():
    swarm = BusinessSwarm()
    res = swarm.run_goal("Build and publish a content marketing campaign on LinkedIn")
    assert res["status"] in ("ok", "dependency_error")
    assert "decomposition" in res and "assignments" in res and "aggregate" in res
    agg = res["aggregate"]
    for key in ("summary", "deliverables", "approvals_required", "failed", "counts"):
        assert key in agg


def _consequential_contract():
    """Pick a real contract that gates an outreach action (deterministic, offline)."""
    for c in BusinessSwarmRegistry().all():
        if ac.ACTION_OUTREACH in c.requires_approval_for:
            return c
    raise AssertionError("no outreach-gated agent in catalog")


def test_approval_required_subtask_not_executed():
    """An outreach subtask hitting a contract gate must be pending, never executed."""
    contract = _consequential_contract()
    subtask = {
        "id": "st1",
        "description": "Run cold outreach to 50 prospects",
        "needed_capability": "outreach",
        "depends_on": [],
    }
    assignments = [{"subtask": subtask, "agent_id": contract.id, "contract": contract}]
    exec_result = execute_run(assignments)
    agg = aggregate(exec_result)

    approvals = agg["approvals_required"]
    assert approvals, "expected the gated subtask in approvals_required"
    assert approvals[0]["requires_approval_for"] == ac.ACTION_OUTREACH
    # Pending, not delivered, and no fabricated output.
    delivered_ids = {d["subtask_id"] for d in agg["deliverables"]}
    assert "st1" not in delivered_ids
    for r in exec_result["results"]:
        if r.get("status") == "pending_approval":
            assert r.get("output") is None


def test_run_goal_never_raises_on_bad_input():
    swarm = BusinessSwarm()
    for bad in [None, "", 123, "   "]:
        res = swarm.run_goal(bad)  # type: ignore[arg-type]
        assert isinstance(res, dict) and "aggregate" in res


def test_singleton_accessor():
    assert get_business_swarm() is get_business_swarm()

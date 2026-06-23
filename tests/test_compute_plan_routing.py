"""Cost-first routing: plan->installed-model resolution + deny-by-default escalation.

Proves the security-critical behaviour of the model-orchestration cost ladder:
  - the local rung resolves to a real installed model@quant (no hardcoded names),
  - external egress (OpenRouter) is OFF unless explicitly enabled AND privacy/online/key allow,
  - offline/privacy block egress and fall back to local (never silent egress),
  - rent_gpu raises a HITL approval card and spends nothing,
  - the per-run model hint never leaks (scope always resets),
  - the LLM client only egresses when the gated provider override is set.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from engine.compute import compute_planner as cp  # noqa: E402
from engine.compute.compute_planner import ComputePlan, assess_compute_needs  # noqa: E402
from core import model_escalation as esc  # noqa: E402
from core import run_model_context as rmc  # noqa: E402


# Increment A - local rung resolves to a real installed model (no hardcodes)

def test_no_hardcoded_model_or_vram_map():
    # The old hardcoded maps must be gone - resolution is delegated to model_lanes.
    assert not hasattr(cp, "_MODEL_VRAM")
    src = Path(cp.__file__).read_text()
    assert "strategy_model = {" not in src


def test_plan_resolves_installed_local_model():
    import os
    from core.model_role_resolver import _installed_models
    installed = _installed_models()
    plan = assess_compute_needs("write a python function to parse json", context_len=40)
    # Strategy may be local OR an escalation rung (if the local coder heavily offloads); either way
    # plan.model is always the INSTALLED local model (the fallback for escalation rungs).
    assert plan.strategy in ("local_tiny", "local_general", "local_reasoning",
                             "local_coder", "openrouter_free", "rent_gpu")
    assert plan.model  # non-empty, resolved by the inventory-aware role resolver
    assert plan.tier in ("FAST", "NORMAL", "HEAVY", "DEEP_THINKING", "CODE")
    # quant is either a concrete quant string or None (Ollama decides) - never a stale guess.
    assert plan.quant is None or isinstance(plan.quant, str)
    # The planner must NEVER name a model that isn't pulled (or the pinned env default).
    if installed:
        default = os.environ.get("OLLAMA_MODEL", "llama3.2")
        assert plan.model in installed or plan.model == default, \
            f"planner picked uninstalled model {plan.model!r}"


def test_simple_goal_uses_fast_tier():
    plan = assess_compute_needs("what is the capital of France", context_len=20)
    assert plan.strategy == "local_tiny"
    assert plan.tier == "FAST"
    assert plan.estimated_cost_usd == 0.0 and plan.needs_approval is False


def test_huge_context_escalates_to_rent_gpu():
    plan = assess_compute_needs("summarise this", context_len=999_999)
    assert plan.strategy == "rent_gpu"
    assert plan.needs_approval is True
    assert plan.model  # still carries a local fallback model


_HEAVY_OFFLOAD = {"model": "qwen2.5-coder:14b", "quant": "q5_K_M",
                  "vram_needed": 9000, "fits": False, "offload_layers": 25}


def test_heavy_offload_triggers_openrouter_strategy(monkeypatch):
    # A local model that only runs via heavy CPU offload should surface free-cloud overflow,
    # even with a short prompt — this is what lets swarm subtasks reach free API keys.
    monkeypatch.delenv("COMPUTE_OFFLOAD_RENT_LAYERS", raising=False)  # rent off by default
    monkeypatch.delenv("COMPUTE_OFFLOAD_OPENROUTER_LAYERS", raising=False)  # default 8
    monkeypatch.setattr(cp, "_resolve_local", lambda strat: dict(_HEAVY_OFFLOAD))
    plan = assess_compute_needs("debug this function", context_len=50)
    assert plan.strategy == "openrouter_free"
    assert plan.needs_approval is False
    assert plan.offload_layers == 25


def test_heavy_offload_rent_is_opt_in(monkeypatch):
    # rent on offload is opt-in (paid path stays quiet by default); enabling the env makes a
    # heavily-offloading model (incl. a swarm subtask) request a rented GPU via HITL.
    monkeypatch.setenv("COMPUTE_OFFLOAD_RENT_LAYERS", "20")
    monkeypatch.setattr(cp, "_resolve_local", lambda strat: dict(_HEAVY_OFFLOAD))
    plan = assess_compute_needs("debug this function", context_len=50)
    assert plan.strategy == "rent_gpu"
    assert plan.needs_approval is True


def test_offload_below_threshold_stays_local(monkeypatch):
    monkeypatch.delenv("COMPUTE_OFFLOAD_RENT_LAYERS", raising=False)
    monkeypatch.setattr(cp, "_resolve_local",
                        lambda strat: {"model": "gemma3:4b-it-qat", "quant": "q4_0",
                                       "vram_needed": 3600, "fits": True, "offload_layers": 0})
    plan = assess_compute_needs("write a haiku", context_len=20)
    assert plan.strategy.startswith("local_")


# helpers

def _ext_plan():
    return ComputePlan(strategy="openrouter_free", model="llama3.2:latest",
                       estimated_cost_usd=0.0, estimated_duration_s=30, vram_needed_mb=2000,
                       needs_approval=False, rationale="test", tier="HEAVY")


def _rent_plan():
    return ComputePlan(strategy="rent_gpu", model="llama3.2:latest",
                       estimated_cost_usd=0.50, estimated_duration_s=120, vram_needed_mb=2000,
                       needs_approval=True, rationale="test", tier="HEAVY")


def _allow_privacy(monkeypatch, allowed=True):
    import neural_brain.config.privacy_mode as pm
    monkeypatch.setattr(pm, "can_use_external_apis", lambda: allowed)


# Increment B - deny-by-default egress

def test_overflow_blocked_when_flag_off(monkeypatch):
    monkeypatch.delenv("MODEL_ALLOW_OPENROUTER_OVERFLOW", raising=False)
    route = esc.apply_compute_plan(_ext_plan())
    assert route.external is False
    assert route.provider is None
    assert route.model == "llama3.2:latest"  # local fallback


def test_overflow_blocked_when_offline(monkeypatch):
    monkeypatch.setenv("MODEL_ALLOW_OPENROUTER_OVERFLOW", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("TURBO_OFFLINE", "1")
    _allow_privacy(monkeypatch, True)
    route = esc.apply_compute_plan(_ext_plan())
    assert route.external is False and route.provider is None


def test_overflow_blocked_when_privacy_denies(monkeypatch):
    monkeypatch.setenv("MODEL_ALLOW_OPENROUTER_OVERFLOW", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TURBO_OFFLINE", raising=False)
    _allow_privacy(monkeypatch, False)
    route = esc.apply_compute_plan(_ext_plan())
    assert route.external is False and route.provider is None


def test_overflow_blocked_when_no_key(monkeypatch):
    monkeypatch.setenv("MODEL_ALLOW_OPENROUTER_OVERFLOW", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TURBO_OFFLINE", raising=False)
    _allow_privacy(monkeypatch, True)
    route = esc.apply_compute_plan(_ext_plan())
    assert route.external is False


def test_overflow_allowed_only_when_all_gates_pass(monkeypatch):
    monkeypatch.setenv("MODEL_ALLOW_OPENROUTER_OVERFLOW", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TURBO_OFFLINE", raising=False)
    monkeypatch.setenv("OPENROUTER_FREE_MODEL", "vendor/free-model:free")
    _allow_privacy(monkeypatch, True)
    route = esc.apply_compute_plan(_ext_plan())
    assert route.external is True
    assert route.provider == "openrouter"
    assert route.model == "vendor/free-model:free"


# Increment B - rent_gpu raises HITL, spends nothing

def test_rent_gpu_emits_hitl_no_spend():
    route = esc.apply_compute_plan(_rent_plan())
    # The run continues locally; no provider, no egress, no auto-spend here.
    assert route.external is False and route.provider is None
    assert route.model == "llama3.2:latest"
    assert route.approval_request_id  # a pending approval was raised
    from core.hitl_gate import get_hitl_gate
    req = get_hitl_gate().get_request(route.approval_request_id)
    assert req is not None
    assert req.get("status") in ("pending", "PENDING")


def test_executed_event_broadcast():
    events = []
    esc.apply_compute_plan(_ext_plan(), broadcast_fn=lambda ev, payload: events.append((ev, payload)))
    assert any(ev == "task:compute_plan_executed" for ev, _ in events)
    _, payload = next(e for e in events if e[0] == "task:compute_plan_executed")
    assert "egress" in payload and payload["egress"] is False


def test_compute_plan_event_includes_resolved_model_metadata(monkeypatch):
    from core.agent_controller import AgentController
    from core.contracts import TaskGraph, TaskNode, ValidationResult

    events = []
    monkeypatch.setattr(AgentController, "_learn_from_conversation", lambda self, goal: None)
    monkeypatch.setattr(AgentController, "_run_context_research_loop", lambda self, goal, run_id: None)
    monkeypatch.setattr(
        AgentController,
        "build_task_graph",
        lambda self, goal, run_id: TaskGraph(
            run_id=run_id,
            goal=goal,
            tasks=[TaskNode(task_id="t1", skill="noop", input={})],
        ),
    )
    monkeypatch.setattr(AgentController, "_feedback_loop", lambda self, goal, task: None)

    controller = AgentController()
    controller.set_broadcast(lambda ev, payload: events.append((ev, payload)))
    controller._executor.execute_graph = lambda graph: graph.tasks
    controller._validator.validate = lambda task: ValidationResult(task.task_id, True, 1.0)
    controller.run_goal("what is the capital of France")

    _, payload = next(e for e in events if e[0] == "task:compute_plan")
    assert payload["tier"] == "FAST"
    assert "quant" in payload
    assert "offload_layers" in payload
    assert "fits_local" in payload


# Increment A - per-run hint seam

def test_preferred_model_scope_sets_and_resets():
    assert rmc.get_preferred_model() is None
    with rmc.preferred_model_scope("gemma3:latest", "openrouter"):
        assert rmc.get_preferred_model() == "gemma3:latest"
        assert rmc.get_preferred_provider() == "openrouter"
    assert rmc.get_preferred_model() is None
    assert rmc.get_preferred_provider() is None


def test_llm_route_honors_preferred_model():
    import engine.inference.llm as L
    with rmc.preferred_model_scope("qwen2.5:7b-instruct", None):
        decision = L._route_model(prompt="hello", context=None, requested_model=None)
        assert decision.chosen_model == "qwen2.5:7b-instruct"
    # explicit model always wins over the hint
    with rmc.preferred_model_scope("qwen2.5:7b-instruct", None):
        decision = L._route_model(prompt="hello", context=None, requested_model="llama3.2")
        assert decision.chosen_model == "llama3.2"


def test_llm_client_routes_to_openrouter_only_when_provider_preferred(monkeypatch):
    from core.orchestrator import LLMClient
    client = LLMClient()
    client.backend = "ollama"
    monkeypatch.setattr(client, "_call_openrouter",
                        lambda **kw: {"output": "OR", "tokens_used": 1, "model": kw.get("model", "")})
    monkeypatch.setattr(client, "_call_ollama",
                        lambda **kw: {"output": "LOCAL", "tokens_used": 1, "model": kw.get("model") or ""})

    with rmc.preferred_model_scope("vendor/free:free", "openrouter"):
        out = client.complete(prompt="hi")
    assert out["output"] == "OR"

    with rmc.preferred_model_scope("llama3.2", None):
        out = client.complete(prompt="hi")
    assert out["output"] == "LOCAL"


def test_generate_delegates_to_openrouter_when_preferred(monkeypatch):
    # Executor path (engine.inference.llm.generate) has no OpenRouter backend, so it must
    # delegate to the gated LLMClient OpenRouter path when the overflow route is active.
    import core.orchestrator as orch
    import engine.inference.llm as L

    class _Fake:
        def complete(self, **kw):
            return {"output": "OR-OUT", "tokens_used": 1, "model": "x"}

    monkeypatch.setattr(orch, "get_llm_client", lambda: _Fake())
    with rmc.preferred_model_scope("vendor/free:free", "openrouter"):
        assert L.generate("hello") == "OR-OUT"

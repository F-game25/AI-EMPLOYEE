"""Compute Planner — assess compute needs before every task (cost-first policy).

Decision flow (cheapest first):
  local_tiny      → FAST tier      simple Q&A, routing, short tasks
  local_general   → NORMAL tier    general multi-step, summaries
  local_reasoning → HEAVY tier     research, analysis, long-form
  local_coder     → CODE tier      code generation / debugging
  openrouter_free → free cloud     exceeds local VRAM budget (egress-gated)
  rent_gpu        → remote GPU     very long tasks, needs HITL approval

This module is the POLICY layer only: it picks the cheapest *rung* and, for local
rungs, resolves the concrete INSTALLED ``model@quant`` that fits live VRAM by delegating
to ``core.model_lanes`` (single source of truth for what's installed + quant/VRAM aware).
It never names an external/rented model — the deny-by-default gating and external
resolution live in ``core.model_escalation``. No model names or VRAM sizes are hardcoded.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger("engine.compute.planner")


@dataclass
class ComputePlan:
    strategy: str            # local_tiny | local_general | local_reasoning | local_coder | openrouter_free | rent_gpu
    model: str               # the LOCAL model that runs / the local fallback for escalation rungs
    estimated_cost_usd: float
    estimated_duration_s: int
    vram_needed_mb: int
    needs_approval: bool
    rationale: str
    tier: str = ""           # model_lanes tier backing this strategy (FAST/NORMAL/HEAVY/CODE)
    quant: str | None = None # resolved quant for the local model (None = Ollama decides)
    offload_layers: int = 0  # CPU-offloaded transformer layers for the local model
    fits_local: bool = True  # whether the local model fits live VRAM without offload


# Map each local strategy to a model_lanes tier (used for the rented-GPU target sizing).
_STRATEGY_TO_TIER: dict[str, str] = {
    "local_tiny":      "FAST",
    "local_general":   "NORMAL",
    "local_reasoning": "HEAVY",
    "local_coder":     "CODE",
}

# Map each local strategy to an installed-aware ROLE (model_roles.json). model_role_resolver
# is the ONLY resolver that checks the live Ollama inventory, so the planner can never name a
# model that isn't actually pulled.
_STRATEGY_TO_ROLE: dict[str, str] = {
    "local_tiny":      "cheap_summary",
    "local_general":   "execution_reasoning",
    "local_reasoning": "execution_reasoning",
    "local_coder":     "coding",
}

# Context-length thresholds (tokens-ish, measured from input) — env-overridable, safe defaults.
_RENT_CONTEXT_TOKENS = int(os.environ.get("COMPUTE_RENT_CONTEXT_TOKENS", "30000"))
_REASONING_CONTEXT_TOKENS = int(os.environ.get("COMPUTE_REASONING_CONTEXT_TOKENS", "12000"))
_GENERAL_CONTEXT_TOKENS = int(os.environ.get("COMPUTE_GENERAL_CONTEXT_TOKENS", "4000"))
_SIMPLE_CONTEXT_TOKENS = int(os.environ.get("COMPUTE_SIMPLE_CONTEXT_TOKENS", "2000"))
_RENT_GPU_EST_USD = float(os.environ.get("COMPUTE_RENT_GPU_EST_USD", "0.50"))

_CODE_KEYWORDS = re.compile(
    r"\b(code|implement|build|write.*function|debug|refactor|script|program|"
    r"class|module|api|endpoint|sql|query|algorithm)\b", re.I
)
_RESEARCH_KEYWORDS = re.compile(
    r"\b(research|analyse|analyze|summarise|summarize|compare|investigate|"
    r"report|explain|literature|trends|market|data)\b", re.I
)
_SIMPLE_KEYWORDS = re.compile(
    r"\b(what is|who is|define|list|translate|convert|calculate|"
    r"format|yes or no|true or false)\b", re.I
)


def _classify_local_tier(goal: str, context_len: int) -> str:
    """Classify a goal into the local strategy it would use (ignoring VRAM escalation)."""
    gl = goal.lower()
    if context_len > _REASONING_CONTEXT_TOKENS:
        return "local_reasoning"
    if _CODE_KEYWORDS.search(gl):
        return "local_coder"
    if _RESEARCH_KEYWORDS.search(gl):
        return "local_reasoning"
    if _SIMPLE_KEYWORDS.search(gl) and context_len < _SIMPLE_CONTEXT_TOKENS:
        return "local_tiny"
    if context_len < _GENERAL_CONTEXT_TOKENS:
        return "local_general"
    return "local_reasoning"


def _classify_goal(goal: str, context_len: int) -> str:
    """Final strategy including size-based escalation (kept for callers/tests)."""
    if context_len > _RENT_CONTEXT_TOKENS:
        return "rent_gpu"
    return _classify_local_tier(goal, context_len)


def _resolve_local(strategy: str) -> dict:
    """Resolve a local strategy to a concrete INSTALLED model@quant (never raises).

    Delegates to ``model_role_resolver.resolve_role`` — the only resolver that checks the
    live Ollama inventory plus quant/VRAM fit. Falls back to the pinned ``OLLAMA_MODEL``
    (guaranteed installed) if the role has no installed model available.
    """
    role = _STRATEGY_TO_ROLE.get(strategy, "execution_reasoning")
    try:
        from core.model_role_resolver import resolve_role
        res = resolve_role(role)
        if res.get("available") and res.get("model"):
            return {"model": res["model"], "quant": res.get("quant"),
                    "vram_needed": int(res.get("vram_needed") or 0),
                    "fits": bool(res.get("fits", True)),
                    "offload_layers": int(res.get("offload_layers") or 0)}
        logger.debug("compute_planner: role %r unavailable (%s) → env default",
                     role, res.get("reason"))
    except Exception as exc:  # noqa: BLE001 — planning must never crash the run
        logger.debug("compute_planner: role resolution failed for %s: %s", strategy, exc)
    # No installed model for the role → run on the pinned default (guaranteed installed).
    return {"model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "quant": None, "vram_needed": 0, "fits": True, "offload_layers": 0}


def assess_compute_needs(goal: str, context_len: int = 0) -> ComputePlan:
    """Return the cheapest ComputePlan sufficient for this goal.

    Resolves the concrete installed local model for the chosen tier and escalates the
    *rung* (not the model) when context is too large for local execution. The local
    model is always carried as the safe fallback for escalation rungs.
    """
    base_strategy = _classify_local_tier(goal, context_len)
    base_tier = _STRATEGY_TO_TIER[base_strategy]
    local = _resolve_local(base_strategy)
    model = local.get("model") or os.environ.get("OLLAMA_MODEL", "llama3.2")
    quant = local.get("quant")
    vram_needed = int(local.get("vram_needed") or 0)
    offload_layers = int(local.get("offload_layers") or 0)
    fits_local = bool(local.get("fits", True))

    # Escalate the rung on resource pressure: a large input context OR a local model that only
    # runs via heavy CPU offload (slow). Thresholds are env-driven (read at call time so they can
    # change at runtime). Egress/spend stay gated downstream in model_escalation, so escalating
    # here is safe — it only SURFACES the option; the deny-by-default gate decides what runs.
    offload_openrouter = int(os.environ.get("COMPUTE_OFFLOAD_OPENROUTER_LAYERS", "8"))
    offload_rent = int(os.environ.get("COMPUTE_OFFLOAD_RENT_LAYERS", "0"))  # 0 = disabled (context-only)
    rent_by_offload = offload_rent > 0 and offload_layers >= offload_rent
    overflow_by_offload = offload_layers >= offload_openrouter
    if context_len > _RENT_CONTEXT_TOKENS or rent_by_offload:
        strategy = "rent_gpu"
    elif not fits_local and (overflow_by_offload or context_len > _REASONING_CONTEXT_TOKENS):
        # Local saturated (heavy offload) or large context → offer free cloud overflow first.
        strategy = "openrouter_free"
    else:
        strategy = base_strategy

    cost = 0.0
    duration = 15
    needs_approval = False
    if strategy == "openrouter_free":
        duration = 30
    elif strategy == "rent_gpu":
        cost = _RENT_GPU_EST_USD
        duration = 120
        needs_approval = True

    rationale = _build_rationale(strategy, model, quant, vram_needed, offload_layers, context_len)
    logger.info("compute_plan goal=%r strategy=%s model=%s@%s vram_needed=%dMB offload=%d",
                goal[:60], strategy, model, quant or "default", vram_needed, offload_layers)

    return ComputePlan(
        strategy=strategy,
        model=model,
        estimated_cost_usd=cost,
        estimated_duration_s=duration,
        vram_needed_mb=vram_needed,
        needs_approval=needs_approval,
        rationale=rationale,
        tier=base_tier,
        quant=quant,
        offload_layers=offload_layers,
        fits_local=fits_local,
    )


def _build_rationale(strategy: str, model: str, quant: str | None, vram_needed: int,
                     offload_layers: int, ctx_len: int) -> str:
    tag = f"{model}@{quant}" if quant else model
    if strategy == "local_tiny":
        return f"Simple task — using {tag} (fast, always hot)"
    if strategy == "local_general":
        return f"General task — using {tag} ({vram_needed}MB VRAM)"
    if strategy == "local_reasoning":
        return f"Research/analysis task — using {tag} ({vram_needed}MB VRAM)"
    if strategy == "local_coder":
        off = f", {offload_layers}-layer CPU offload" if offload_layers else ""
        return f"Code task — using {tag} ({vram_needed}MB VRAM{off})"
    if strategy == "openrouter_free":
        return (f"Local model {tag} runs only via {offload_layers}-layer CPU offload (slow) or "
                f"context is large — offering OpenRouter free-tier overflow "
                f"(no cost; egress-gated, local fallback)")
    if strategy == "rent_gpu":
        reason = (f"context {ctx_len} tokens" if ctx_len > _RENT_CONTEXT_TOKENS
                  else f"{offload_layers}-layer CPU offload")
        return (f"Local execution constrained ({reason}) — remote GPU recommended "
                f"(${_RENT_GPU_EST_USD:.2f} est). Requires approval; falls back to {tag} locally.")
    return tag

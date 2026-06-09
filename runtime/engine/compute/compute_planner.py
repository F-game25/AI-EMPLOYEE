"""Compute Planner — assess compute needs before every task.

Decision flow (cheapest first):
  local_tiny      → llama3.2        simple Q&A, routing, short tasks
  local_general   → gemma3          general multi-step, summaries
  local_reasoning → qwen2.5:7b     research, analysis, long-form
  local_coder     → qwen2.5-coder  code generation / debugging
  openrouter_free → llama-3.1-8b   exceeds local VRAM budget
  rent_gpu        → remote         very long tasks, needs HITL approval
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("engine.compute.planner")


@dataclass
class ComputePlan:
    strategy: str            # local_tiny | local_general | local_reasoning | local_coder | openrouter_free | rent_gpu
    model: str
    estimated_cost_usd: float
    estimated_duration_s: int
    vram_needed_mb: int
    needs_approval: bool
    rationale: str


_STRATEGY_ORDER = [
    "local_tiny",
    "local_general",
    "local_reasoning",
    "local_coder",
    "openrouter_free",
    "rent_gpu",
]

_MODEL_VRAM: dict[str, int] = {
    "llama3.2":               2000,
    "gemma3":                 3300,
    "qwen2.5:7b-instruct":   4700,
    "qwen2.5-coder:14b":     9000,  # with offload: ~6500 GPU + CPU
    "meta-llama/llama-3.1-8b-instruct:free": 0,  # remote
}

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


def _classify_goal(goal: str, context_len: int) -> str:
    """Classify goal into a strategy tier."""
    gl = goal.lower()
    if context_len > 30000:
        return "rent_gpu"
    if context_len > 12000:
        return "local_reasoning"
    if _CODE_KEYWORDS.search(gl):
        return "local_coder"
    if _RESEARCH_KEYWORDS.search(gl):
        return "local_reasoning"
    if _SIMPLE_KEYWORDS.search(gl) and context_len < 2000:
        return "local_tiny"
    if context_len < 4000:
        return "local_general"
    return "local_reasoning"


def assess_compute_needs(goal: str, context_len: int = 0) -> ComputePlan:
    """Return the cheapest ComputePlan sufficient for this goal.

    Checks available VRAM against model requirement; escalates tier
    if local VRAM is insufficient.
    """
    strategy = _classify_goal(goal, context_len)

    # Get live VRAM budget
    free_vram_mb = 99999
    max_vram_mb = 99999
    try:
        from engine.compute.resource_manager import get_resource_manager
        rm = get_resource_manager()
        free_vram_mb = rm.specs.vram_free_mb
        max_vram_mb = rm.budget.max_vram_mb
    except Exception:
        pass

    usable_vram = min(free_vram_mb, max_vram_mb)

    # Map strategy → model
    strategy_model = {
        "local_tiny":      "llama3.2",
        "local_general":   "gemma3",
        "local_reasoning": "qwen2.5:7b-instruct",
        "local_coder":     "qwen2.5-coder:14b",
        "openrouter_free": "meta-llama/llama-3.1-8b-instruct:free",
        "rent_gpu":        "qwen2.5-coder:14b",  # on rented GPU, no VRAM limit
    }

    # Escalate if model doesn't fit in usable VRAM (with offload tolerance for 14b)
    for tier in _STRATEGY_ORDER[_STRATEGY_ORDER.index(strategy):]:
        m = strategy_model[tier]
        needed = _MODEL_VRAM.get(m, 0)
        if tier in ("openrouter_free", "rent_gpu"):
            strategy = tier
            break
        if needed == 0 or needed <= usable_vram + 2000:  # +2GB tolerance for offload
            strategy = tier
            break
        logger.debug("escalate: %s needs %dMB VRAM, only %dMB usable", m, needed, usable_vram)

    model = strategy_model[strategy]
    vram_needed = _MODEL_VRAM.get(model, 0)

    cost = 0.0
    duration = 15
    needs_approval = False
    if strategy == "openrouter_free":
        cost = 0.0
        duration = 30
    elif strategy == "rent_gpu":
        cost = 0.50
        duration = 120
        needs_approval = True

    rationale = _build_rationale(strategy, model, usable_vram, vram_needed, context_len)
    logger.info("compute_plan goal=%r strategy=%s model=%s vram_needed=%dMB", goal[:60], strategy, model, vram_needed)

    return ComputePlan(
        strategy=strategy,
        model=model,
        estimated_cost_usd=cost,
        estimated_duration_s=duration,
        vram_needed_mb=vram_needed,
        needs_approval=needs_approval,
        rationale=rationale,
    )


def _build_rationale(strategy: str, model: str, usable_vram: int, vram_needed: int, ctx_len: int) -> str:
    if strategy == "local_tiny":
        return f"Simple task — using {model} (fast, always hot)"
    if strategy == "local_general":
        return f"General task — using {model} ({vram_needed}MB VRAM, {usable_vram}MB available)"
    if strategy == "local_reasoning":
        return f"Research/analysis task — using {model} ({vram_needed}MB VRAM)"
    if strategy == "local_coder":
        return f"Code task — using {model} (with CPU offload if needed)"
    if strategy == "openrouter_free":
        return f"Local VRAM insufficient ({usable_vram}MB) — routing to OpenRouter free tier (no cost)"
    if strategy == "rent_gpu":
        return f"Context too large ({ctx_len} tokens) or task requires more VRAM — remote GPU recommended ($0.50 est). Requires approval."
    return model

"""Model tiers — hardware-dynamic task → model selection.

Nothing here is a fixed LLM. Every tier resolves to the best model the machine can
actually run *right now*, driven by ``ResourceManager`` (VRAM/RAM budget). This sits
ON TOP of existing routing (``model_routing`` tier/wavefield); it does not replace it.

Tiers
-----
  FAST           quick routing / classification / short chat   — smallest, always hot
  NORMAL         general work / balanced chat                   — mid model, hot
  HEAVY          hard analysis / planning / long context        — largest reasoner that fits
  DEEP_THINKING  the hardest reasoning / deep synthesis         — biggest model the box can run

  CODE           code generation / review                       — ALWAYS a coder model
                 (qwen2.5-coder family, never a general llama); degrades to a smaller
                 coder, never to a non-coder.

Selection is dynamic:
  1. explicit env override per tier (e.g. ``MODEL_TIER_HEAVY``, ``MODEL_TIER_CODE``)
  2. largest model in the tier's candidate ladder whose VRAM need fits the live budget
  3. smallest candidate as a last resort (CPU offload)

Usage
-----
    from core.model_lanes import resolve_tier, tier_for_task, TIER_FAST, TIER_CODE
    model = resolve_tier(TIER_FAST)
    model = resolve_tier(tier_for_task("coding"))   # -> a coder model
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

TIER_FAST = "FAST"
TIER_NORMAL = "NORMAL"
TIER_HEAVY = "HEAVY"
TIER_DEEP = "DEEP_THINKING"
TIER_CODE = "CODE"

# The 4 size tiers, smallest→largest. CODE is separate (specialised, not a size tier).
SIZE_TIERS = (TIER_FAST, TIER_NORMAL, TIER_HEAVY, TIER_DEEP)
ALL_TIERS = (TIER_FAST, TIER_NORMAL, TIER_HEAVY, TIER_DEEP, TIER_CODE)

# Candidate ladders (model, vram_mb_needed), ordered LARGEST→SMALLEST.
# resolve_tier walks each ladder and picks the first model that fits the live budget.
# These are *candidates the system may use*, not fixed choices — the hardware decides.
_LADDERS: dict[str, list[tuple[str, int]]] = {
    # FAST: tiny, must run anywhere (even CPU-only).
    TIER_FAST: [
        ("llama3.2:latest", 2000),
    ],
    # NORMAL: balanced general model.
    TIER_NORMAL: [
        ("qwen2.5:7b-instruct", 4700),
        ("gemma3:latest", 3300),
        ("llama3.2:latest", 2000),
    ],
    # HEAVY: strongest reasoner that fits.
    TIER_HEAVY: [
        ("qwen2.5:14b-instruct", 9000),
        ("qwen3.5", 6600),
        ("qwen2.5:7b-instruct", 4700),
        ("gemma3:latest", 3300),
        ("llama3.2:latest", 2000),
    ],
    # DEEP_THINKING: the biggest the box can run; falls all the way down if needed.
    TIER_DEEP: [
        ("llama3.3:70b", 43000),
        ("qwen2.5:32b-instruct", 20000),
        ("qwen2.5:14b-instruct", 9000),
        ("qwen3.5", 6600),
        ("qwen2.5:7b-instruct", 4700),
        ("gemma3:latest", 3300),
        ("llama3.2:latest", 2000),
    ],
    # CODE: ALWAYS a coder model. Never degrades to a general model.
    TIER_CODE: [
        ("qwen2.5-coder:32b", 20000),
        ("qwen2.5-coder:14b", 9000),
        ("qwen2.5-coder:7b", 4700),
        ("qwen2.5-coder:3b", 2200),
        ("qwen2.5-coder:1.5b", 1200),
    ],
}

# Free-form task_type → tier.
_TASK_TO_TIER: dict[str, str] = {
    "routing": TIER_FAST, "classification": TIER_FAST, "fast": TIER_FAST, "short": TIER_FAST,
    "chat": TIER_NORMAL, "general": TIER_NORMAL, "normal": TIER_NORMAL, "default": TIER_NORMAL,
    "analysis": TIER_HEAVY, "planning": TIER_HEAVY, "reasoning": TIER_HEAVY, "heavy": TIER_HEAVY,
    "research": TIER_DEEP, "synthesis": TIER_DEEP, "deep": TIER_DEEP, "deep_thinking": TIER_DEEP,
    "code": TIER_CODE, "coding": TIER_CODE, "engineering": TIER_CODE, "review": TIER_CODE,
}


def tier_for_task(task_type: str | None) -> str:
    """Map a free-form task_type to a tier. Unknown/empty → NORMAL."""
    return _TASK_TO_TIER.get((task_type or "").strip().lower(), TIER_NORMAL)


def _usable_vram_mb() -> int | None:
    """Live usable VRAM budget in MB; None if ResourceManager unavailable."""
    try:
        from engine.compute.resource_manager import get_resource_manager
        b = get_resource_manager().budget
        # max_vram_mb = the ceiling the system may use (offload makes "fit" generous).
        return int(getattr(b, "max_vram_mb", 0) or 0)
    except Exception as exc:  # noqa: BLE001 — never break resolution
        logger.debug("model_lanes: VRAM budget unavailable: %s", exc)
        return None


def resolve_tier(tier: str) -> str:
    """Resolve a tier to the best concrete model the hardware can run.

    Order: env override → largest candidate that fits live VRAM → smallest candidate.
    A coder tier always returns a coder model.
    """
    tier = (tier or TIER_NORMAL).strip().upper()
    if tier not in _LADDERS:
        tier = TIER_NORMAL

    override = os.environ.get(f"MODEL_TIER_{tier}")
    if override:
        return override.strip()

    ladder = _LADDERS[tier]
    vram = _usable_vram_mb()
    if vram is None:
        # No hardware info: be safe — pick the SMALLEST candidate (runs anywhere).
        return ladder[-1][0]

    # Allow CPU offload headroom: a model "fits" if its need is within budget,
    # or within 2x budget for the offloadable larger models (Ollama spills to RAM/CPU).
    for model, need in ladder:  # largest → smallest
        if need <= vram or need <= vram * 2:
            return model
    return ladder[-1][0]


def resolve_for_task(task_type: str | None) -> str:
    """Convenience: task_type → tier → model."""
    return resolve_tier(tier_for_task(task_type))


def tier_models() -> dict[str, str]:
    """Current resolved model per tier — for warmup, /api/models, diagnostics."""
    return {tier: resolve_tier(tier) for tier in ALL_TIERS}


def hot_tier_models() -> list[str]:
    """Models that should stay resident (keep_alive=-1): FAST + NORMAL."""
    seen: list[str] = []
    for tier in (TIER_FAST, TIER_NORMAL):
        m = resolve_tier(tier)
        if m not in seen:
            seen.append(m)
    return seen

"""Named model lanes — a thin, explicit task-type → local model abstraction.

This sits ON TOP of the existing routing (``model_routing.select_model_route`` for
tier/wavefield, ``ResourceManager.select_llm_stack`` for hardware-aware picks). It
does NOT replace them. Callers that just want "the right local model for this kind
of work" ask for a lane; the lane resolves to a concrete model name, honouring:

  1. an explicit env override per lane (e.g. ``MODEL_LANE_CODE``), then
  2. the hardware-aware stack from ResourceManager (so an 8 GB card and a 24 GB
     card get different coder models), then
  3. a static, installed-model default.

Lanes
-----
  FAST       quick routing / classification / short Q&A     (smallest, always hot)
  DEFAULT    general chat / balanced work                   (always hot)
  CODE       code generation / review                       (coder model, on demand)
  REASONING  multi-step analysis / planning                 (mid model, on demand)
  DEEP       hardest reasoning / long synthesis             (largest available)

Usage
-----
    from core.model_lanes import resolve_lane, lane_for_task, LANE_FAST
    model = resolve_lane(LANE_FAST)                # -> "llama3.2:latest"
    model = resolve_lane(lane_for_task("coding"))  # -> coder model
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

LANE_FAST = "FAST"
LANE_DEFAULT = "DEFAULT"
LANE_CODE = "CODE"
LANE_REASONING = "REASONING"
LANE_DEEP = "DEEP"

ALL_LANES = (LANE_FAST, LANE_DEFAULT, LANE_CODE, LANE_REASONING, LANE_DEEP)

# Static fallbacks — installed models confirmed in resource_manager._MODEL_CATALOGUE.
# Only used when neither an env override nor the hardware stack supplies a value.
_LANE_DEFAULTS: dict[str, str] = {
    LANE_FAST:      "llama3.2:latest",
    LANE_DEFAULT:   "gemma3:latest",
    LANE_CODE:      "qwen2.5-coder:14b",
    LANE_REASONING: "qwen2.5:7b-instruct",
    LANE_DEEP:      "llama3.3:latest",
}

# task_type (as used across agents / ai_router) -> lane
_TASK_TO_LANE: dict[str, str] = {
    "routing": LANE_FAST, "classification": LANE_FAST, "fast": LANE_FAST,
    "chat": LANE_DEFAULT, "general": LANE_DEFAULT, "default": LANE_DEFAULT,
    "code": LANE_CODE, "coding": LANE_CODE, "engineering": LANE_CODE,
    "reasoning": LANE_REASONING, "analysis": LANE_REASONING, "planning": LANE_REASONING,
    "research": LANE_DEEP, "synthesis": LANE_DEEP, "deep": LANE_DEEP,
}

# Which ResourceManager stack key each lane prefers (hardware-aware layer).
_LANE_TO_STACK_KEY: dict[str, str] = {
    LANE_FAST: "primary",
    LANE_DEFAULT: "primary",
    LANE_CODE: "coder",
    LANE_REASONING: "reasoning",
    LANE_DEEP: "reasoning",  # DEEP wants the strongest; stack tops out at reasoning
}


def lane_for_task(task_type: str | None) -> str:
    """Map a free-form task_type to a lane. Unknown/empty -> DEFAULT."""
    return _TASK_TO_LANE.get((task_type or "").strip().lower(), LANE_DEFAULT)


def _hardware_stack() -> dict | None:
    """Best-effort hardware-aware model stack; None if unavailable."""
    try:
        from engine.compute.resource_manager import get_resource_manager
        return get_resource_manager().select_llm_stack()
    except Exception as exc:  # noqa: BLE001 — never break resolution on this
        logger.debug("model_lanes: resource stack unavailable: %s", exc)
        return None


def resolve_lane(lane: str) -> str:
    """Resolve a lane name to a concrete model. Order: env override → hardware stack → default."""
    lane = (lane or LANE_DEFAULT).strip().upper()
    if lane not in _LANE_DEFAULTS:
        lane = LANE_DEFAULT

    env_override = os.environ.get(f"MODEL_LANE_{lane}")
    if env_override:
        return env_override.strip()

    stack = _hardware_stack()
    if stack:
        key = _LANE_TO_STACK_KEY[lane]
        # CODE only honours the coder slot if the box can actually run it.
        if lane == LANE_CODE and not stack.get("can_run_coder", True):
            return resolve_lane(LANE_REASONING)
        model = stack.get(key)
        if model:
            return model

    return _LANE_DEFAULTS[lane]


def resolve_for_task(task_type: str | None) -> str:
    """Convenience: task_type -> lane -> model."""
    return resolve_lane(lane_for_task(task_type))


def lane_models() -> dict[str, str]:
    """Current resolved model per lane — for warmup, /api/models, and diagnostics."""
    return {lane: resolve_lane(lane) for lane in ALL_LANES}


def hot_lane_models() -> list[str]:
    """Models that should stay resident (keep_alive=-1): the always-hot lanes."""
    seen: list[str] = []
    for lane in (LANE_FAST, LANE_DEFAULT):
        m = resolve_lane(lane)
        if m not in seen:
            seen.append(m)
    return seen

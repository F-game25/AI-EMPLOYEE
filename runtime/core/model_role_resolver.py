"""Role → concrete *installed* model resolver + the hard PC-control gate check.

``model_lanes.model_and_quant_for_role()`` picks a model by VRAM fit but does NOT
check whether the model is actually pulled in Ollama. This resolver adds that:
a role is only ``available`` when a preferred model meeting its quant floor is
INSTALLED (and either fits or can offload). The ``execution_reasoning`` role
hard-gates PC-control / browser actions — if no execution-grade model is
installed, those actions are blocked with an install suggestion, never run on a
weak model (the core safety requirement, plan §3.1 / §5 Phase A5).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("model_role_resolver")


def _installed_models() -> set[str]:
    """Set of installed Ollama model names (tagged + bare), live from /api/tags."""
    try:
        from engine.compute.hardware_profiler import ollama_inventory
        names: set[str] = set()
        for m in (ollama_inventory() or []):
            n = m.get("name") or m.get("model")
            if n:
                names.add(n)
                names.add(n.split(":")[0])  # also the bare name (e.g. "gemma3")
        return names
    except Exception as exc:  # noqa: BLE001 — never break the gate
        logger.debug("ollama inventory unavailable: %s", exc)
        return set()


def _is_installed(model: str, installed: set[str]) -> bool:
    # ``installed`` holds both tagged names ("gemma3:latest") and bare names
    # ("gemma3"). A specific tag (e.g. "gemma3:4b-it-qat") must match exactly — it
    # is NOT satisfied by a different tag of the same base. An untagged preferred
    # ("qwen3.5") matches via the bare name we added for each installed model.
    return model in installed


def resolve_role(role: str) -> dict[str, Any]:
    """Resolve a role to an INSTALLED model@quant that meets its quant floor.

    Returns {role, model, quant, vram_needed, fits, offload_layers, installed,
    available, min_quant, on_unavailable, reason, install_suggestion?}. A fully
    fitting installed model wins; else an installed model that offloads; else
    ``available=False`` with an ``install_suggestion`` (never a silent downgrade).
    """
    from core import model_lanes as ml

    spec = ml._model_roles().get(role) or {}
    preferred = spec.get("preferred_models") or []
    min_quant = spec.get("min_quant")
    on_unavailable = spec.get("on_unavailable", "block_or_remote")
    headroom = getattr(ml, "_KV_SELECT_HEADROOM_MB", 800)
    free = (ml._live_free_vram_mb() if hasattr(ml, "_live_free_vram_mb")
            else ml._usable_vram_mb())
    installed = _installed_models()

    offload_candidate: dict[str, Any] | None = None
    for model in preferred:
        if not _is_installed(model, installed):
            continue
        for quant, vram in ml._quant_ladder(model):  # highest → lowest quant
            if not ml._quant_at_least(quant, min_quant):
                continue
            fits = (free is None) or (vram + headroom <= free)
            cand = {
                "role": role, "model": model, "quant": quant, "vram_needed": vram,
                "fits": fits, "installed": True, "available": True,
                "min_quant": min_quant, "on_unavailable": on_unavailable,
                "offload_layers": 0 if fits else ml._offload_layers(model, quant, vram, free),
            }
            if fits:
                return {**cand, "reason": f"{model}@{quant} installed and fits VRAM"}
            if offload_candidate is None:
                offload_candidate = {
                    **cand,
                    "reason": f"{model}@{quant} installed but offloads "
                              f"{cand['offload_layers']} layers (slow)"}
    if offload_candidate is not None:
        return offload_candidate

    return {
        "role": role, "model": None, "quant": None, "vram_needed": None,
        "fits": False, "installed": False, "available": False,
        "min_quant": min_quant, "on_unavailable": on_unavailable,
        "install_suggestion": preferred[0] if preferred else None,
        "reason": (f"no installed model for role '{role}' meets quant floor "
                   f"{min_quant}; pull {preferred[0]}" if preferred
                   else f"no models configured for role '{role}'"),
    }


def execution_reasoning_ready() -> dict[str, Any]:
    """Hard-gate status for PC-control / browser / forge action decisions."""
    return resolve_role("execution_reasoning")

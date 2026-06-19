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

import functools
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Config files (single source of truth — no model names hardcoded in logic).
_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
_QUANT_PROFILES_PATH = _CONFIG_DIR / "model_quant_profiles.json"
_MODEL_ROLES_PATH = _CONFIG_DIR / "model_roles.json"

# KV-cache headroom (MB) to reserve when ranking quant fit. The full per-request
# KV math lives in engine.compute.vram_budget; this is a cheap floor for selection.
_KV_SELECT_HEADROOM_MB = 600

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
    """Resolve a tier to the best concrete LOCAL model the hardware can run.

    Order: env override → largest candidate that fits live VRAM → smallest candidate.
    A coder tier always returns a coder model. This is the free, no-approval path.
    For paid external-API / rented-remote options use ``resolve_target``.
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


# ── Quant-aware resolution (config-driven, measured-VRAM) ─────────────────────
# These extend resolve_tier() with quant selection driven by model_quant_profiles
# + live free VRAM. resolve_tier() stays backward-compatible (returns .model).

@functools.lru_cache(maxsize=1)
def _quant_profiles() -> dict:
    """{model: {quants: {quant: vram_mb}, arch, ...}} from model_quant_profiles.json."""
    try:
        with open(_QUANT_PROFILES_PATH, "r") as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as exc:  # noqa: BLE001 — never break resolution
        logger.warning("model_lanes: quant profiles load failed: %s", exc)
        return {}


@functools.lru_cache(maxsize=1)
def _model_roles() -> dict:
    """{role: {...}} from model_roles.json."""
    try:
        with open(_MODEL_ROLES_PATH, "r") as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("model_lanes: model roles load failed: %s", exc)
        return {}


def _live_free_vram_mb() -> int | None:
    """Live MEASURED free VRAM (hardware_profiler), falling back to the RM budget."""
    try:
        from engine.compute.hardware_profiler import live_vram_mb
        v = live_vram_mb()
        if v is not None:
            return v
    except Exception as exc:  # noqa: BLE001
        logger.debug("model_lanes: hardware_profiler unavailable: %s", exc)
    return _usable_vram_mb()


def _quant_ladder(model: str) -> list[tuple[str, int]]:
    """Model's quant ladder as (quant, vram_mb) ordered LARGEST→SMALLEST VRAM."""
    quants = (_quant_profiles().get(model) or {}).get("quants") or {}
    return sorted(quants.items(), key=lambda kv: kv[1], reverse=True)


_QUANT_RANK = ["q2_K", "q3_K_M", "q4_0", "q4_K_M", "q5_K_M", "q6_K", "q8_0", "f16", "fp16"]


def _quant_at_least(quant: str, floor: str | None) -> bool:
    """True if ``quant`` meets/exceeds ``floor`` on the quality ladder."""
    if not floor:
        return True
    q, f = quant.lower(), floor.lower()
    rl = [r.lower() for r in _QUANT_RANK]
    if q not in rl or f not in rl:
        return True  # unknown quant — don't block, let VRAM decide
    return rl.index(q) >= rl.index(f)


def _offload_layers(model: str, quant: str, vram_needed: int, free: int | None) -> int:
    """How many layers spill to CPU if this quant doesn't fully fit (0 = fully fits)."""
    if free is None or vram_needed + _KV_SELECT_HEADROOM_MB <= free:
        return 0
    n_layers = int(((_quant_profiles().get(model) or {}).get("arch") or {}).get("n_layers", 0) or 0)
    if not n_layers:
        return 0
    per_layer = max(vram_needed / n_layers, 1.0)
    deficit = (vram_needed + _KV_SELECT_HEADROOM_MB) - free
    return min(n_layers, max(0, int((deficit + per_layer - 1) // per_layer)))


def resolve_tier_with_quant(tier: str, *, min_quant: str | None = None) -> dict:
    """Resolve a tier to a concrete ``model@quant`` that fits live free VRAM.

    Walks the tier's model ladder (largest→smallest), and for each model walks its
    quant ladder (highest→lowest quant), picking the FIRST quant whose
    ``vram + KV headroom`` fits live free VRAM and meets ``min_quant``. If nothing
    fully fits, returns the largest model's smallest acceptable quant with
    ``fits=False`` + ``offload_layers`` so the caller can offload (never OOM).

    Returns {model, quant, vram_needed, fits, offload_layers}.
    """
    tier = (tier or TIER_NORMAL).strip().upper()
    if tier not in _LADDERS:
        tier = TIER_NORMAL

    free = _live_free_vram_mb()
    profiles = _quant_profiles()
    fallback: dict | None = None  # best "doesn't fully fit" candidate (largest model)

    for model, _legacy_need in _LADDERS[tier]:  # largest → smallest model
        ladder = _quant_ladder(model)
        if not ladder:
            continue  # no profile for this model — skip in quant-aware path
        for quant, vram in ladder:  # highest → lowest quant
            if not _quant_at_least(quant, min_quant):
                continue
            offload = _offload_layers(model, quant, vram, free)
            fits = (free is None) or (vram + _KV_SELECT_HEADROOM_MB <= free)
            if fits:
                return {"model": model, "quant": quant, "vram_needed": vram,
                        "fits": True, "offload_layers": 0}
            if fallback is None:
                fallback = {"model": model, "quant": quant, "vram_needed": vram,
                            "fits": False, "offload_layers": offload}

    if fallback is not None:
        return fallback
    # No profiled model in this tier — degrade to the legacy resolver's choice.
    legacy = resolve_tier(tier)
    return {"model": legacy, "quant": None, "vram_needed": None,
            "fits": None, "offload_layers": 0}


def model_and_quant_for_role(role: str) -> dict:
    """Resolve a ROLE (model_roles.json) to a concrete model@quant.

    Walks the role's ``preferred_models`` best→fallback; for each, picks the highest
    quant >= the role's ``min_quant`` that fits live free VRAM. Honours
    ``never_degrade_to_general`` only implicitly (preferred_models for coding lists
    coder models exclusively). Returns:
        {role, model, quant, vram_needed, fits, offload_layers, min_quant,
         available, reason, on_unavailable}
    ``available=False`` means no preferred model meets the quant floor AND fits —
    the caller must honour ``on_unavailable`` (never silently downgrade).
    """
    spec = _model_roles().get(role)
    if not spec:
        return {"role": role, "model": None, "quant": None, "available": False,
                "reason": f"unknown role '{role}'", "on_unavailable": "block_or_remote"}

    min_quant = spec.get("min_quant")
    free = _live_free_vram_mb()
    preferred = spec.get("preferred_models") or []
    profiles = _quant_profiles()

    fits_best: dict | None = None
    offload_best: dict | None = None  # meets quant floor but needs offload

    for model in preferred:
        for quant, vram in _quant_ladder(model):  # highest → lowest quant
            if not _quant_at_least(quant, min_quant):
                continue
            fits = (free is None) or (vram + _KV_SELECT_HEADROOM_MB <= free)
            cand = {"model": model, "quant": quant, "vram_needed": vram,
                    "fits": fits,
                    "offload_layers": 0 if fits else _offload_layers(model, quant, vram, free)}
            if fits:
                fits_best = cand
                break
            if offload_best is None:
                offload_best = cand
        if fits_best is not None:
            break

    base = {"role": role, "min_quant": min_quant,
            "on_unavailable": spec.get("on_unavailable", "block_or_remote")}
    if fits_best is not None:
        return {**base, **fits_best, "available": True,
                "reason": f"{fits_best['model']}@{fits_best['quant']} fits free VRAM"}
    if offload_best is not None:
        return {**base, **offload_best, "available": True,
                "reason": f"{offload_best['model']}@{offload_best['quant']} via "
                          f"{offload_best['offload_layers']}-layer CPU offload (no full GPU fit)"}
    return {**base, "model": None, "quant": None, "vram_needed": None,
            "fits": False, "offload_layers": 0, "available": False,
            "reason": f"no preferred model for '{role}' meets {min_quant} and fits "
                      f"(free={free}MB); honour on_unavailable"}


def best_quant_for_model(model: str, *, min_quant: str | None = None) -> dict:
    """Pick the best quant of a SPECIFIC ``model`` that fits live free VRAM.

    Used by the inference path (A4) to add quant-awareness to a model the router
    already chose — it does NOT re-select the model. Walks the model's quant ladder
    highest→lowest and returns the highest quant >= ``min_quant`` that fits free VRAM;
    else the smallest acceptable quant with ``fits=False`` + ``offload_layers`` (never
    OOM). If the model has no quant profile, returns ``quant=None`` so the caller keeps
    its current behaviour (Ollama decides placement).

    Returns {model, quant, vram_needed, fits, offload_layers}.
    """
    free = _live_free_vram_mb()
    fallback: dict | None = None
    for quant, vram in _quant_ladder(model):  # highest → lowest quant
        if not _quant_at_least(quant, min_quant):
            continue
        fits = (free is None) or (vram + _KV_SELECT_HEADROOM_MB <= free)
        if fits:
            return {"model": model, "quant": quant, "vram_needed": vram,
                    "fits": True, "offload_layers": 0}
        if fallback is None:
            fallback = {"model": model, "quant": quant, "vram_needed": vram,
                        "fits": False, "offload_layers": _offload_layers(model, quant, vram, free)}
    if fallback is not None:
        return fallback
    return {"model": model, "quant": None, "vram_needed": None,
            "fits": None, "offload_layers": 0}


# ── Execution targets (local / external API / rented remote) ──────────────────
# Per requirement: CODE and heavy/deep work may also run on an EXTERNAL API
# (Claude/GPT) or on RENTED remote compute (a much bigger local model on a rented
# GPU). Both are PAID + require user approval — never auto-selected silently.

TARGET_LOCAL = "local"
TARGET_EXTERNAL_API = "external_api"   # Claude / GPT etc. — paid
TARGET_RENTED_REMOTE = "rented_remote"  # rent a GPU, run a big local model — paid

# External-API provider for the companion's CODE / DEEP / HEAVY work.
# COMPANION_EXTERNAL_PROVIDER selects which paid provider backs those tiers:
#   anthropic (default) | openai | deepseek
# NORMAL/FAST stay on OpenAI (cheap, fast) regardless — they are not the
# heavy coding/reasoning lanes this switch governs.
_DEFAULT_EXTERNAL_PROVIDER = "anthropic"


def external_api_model_for(tier: str, provider: str | None = None) -> tuple[str, str]:
    """Return (provider, model) for a tier's external-API target.

    Pure + deterministic: reads env at call time, no module-level caching, so
    tests can set os.environ and call this directly. ``provider`` overrides
    COMPANION_EXTERNAL_PROVIDER for the heavy lanes (CODE/DEEP/HEAVY).
    """
    tier = (tier or TIER_NORMAL).strip().upper()
    heavy_provider = (
        provider
        or os.environ.get("COMPANION_EXTERNAL_PROVIDER", _DEFAULT_EXTERNAL_PROVIDER)
    ).strip().lower() or _DEFAULT_EXTERNAL_PROVIDER

    # NORMAL/FAST: always cheap OpenAI, not governed by the heavy-lane switch.
    if tier in (TIER_NORMAL, TIER_FAST):
        return ("openai", os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))

    # Heavy lanes (CODE / DEEP / HEAVY) honour the selected provider.
    if heavy_provider == "deepseek":
        if tier == TIER_CODE:
            return ("deepseek", os.environ.get("DEEPSEEK_CODE_MODEL", "deepseek-coder"))
        # DEEP / HEAVY → reasoner
        return ("deepseek", os.environ.get("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"))

    if heavy_provider == "openai":
        if tier == TIER_CODE:
            return ("openai", os.environ.get("OPENAI_CODE_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o")))
        return ("openai", os.environ.get("OPENAI_MODEL", "gpt-4o"))

    # Default: anthropic
    if tier == TIER_CODE:
        return ("anthropic", os.environ.get("CLAUDE_CODE_MODEL", "claude-opus-4-6"))
    return ("anthropic", os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"))


def _build_external_api_models() -> dict[str, tuple[str, str]]:
    """Build the per-tier external-API map honouring COMPANION_EXTERNAL_PROVIDER."""
    return {tier: external_api_model_for(tier) for tier in ALL_TIERS}


# Best external-API model per tier (env-overridable). Coder tier prefers a coding model.
# Built at import time from external_api_model_for(); resolve_target() rebuilds it
# per-call so a runtime env change to COMPANION_EXTERNAL_PROVIDER takes effect.
_EXTERNAL_API_MODELS: dict[str, tuple[str, str]] = _build_external_api_models()

# Biggest model worth renting a GPU for, per tier (the "much heavier local model").
_RENTED_REMOTE_MODELS: dict[str, str] = {
    TIER_CODE: "qwen2.5-coder:32b",
    TIER_DEEP: "llama3.3:70b",
    TIER_HEAVY: "qwen2.5:32b-instruct",
    TIER_NORMAL: "qwen2.5:14b-instruct",
    TIER_FAST: "qwen2.5:7b-instruct",
}


def _provider_key_present(provider: str) -> bool:
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if provider == "deepseek":
        return bool(os.environ.get("DEEPSEEK_API_KEY"))
    return False


def resolve_target(
    tier: str,
    *,
    prefer: str = TARGET_LOCAL,
    allow_paid: bool = False,
) -> dict:
    """Resolve a tier to a concrete execution target.

    Returns a dict:
      {
        target: 'local'|'external_api'|'rented_remote',
        provider: str|None,         # for external_api
        model: str,
        requires_approval: bool,    # paid targets always need approval
        requires_payment: bool,
        rationale: str,
      }

    Rules:
      - ``prefer='local'`` (default) → always the free local model, no approval.
      - ``prefer='external_api'`` / ``'rented_remote'`` are PAID; only honoured when
        ``allow_paid=True`` (the user approved + will pay). Otherwise we fall back to
        local and flag that a paid upgrade is available (so the UI can offer it).
      - Paid targets always come back with requires_approval=True + requires_payment=True;
        the SafetyGate / HITL + Compute approval flow must clear them before execution.
    """
    tier = (tier or TIER_NORMAL).strip().upper()
    if tier not in _LADDERS:
        tier = TIER_NORMAL

    if prefer == TARGET_EXTERNAL_API and allow_paid:
        # Rebuild per-call so a runtime COMPANION_EXTERNAL_PROVIDER change is honoured.
        provider, model = external_api_model_for(tier)
        return {
            "target": TARGET_EXTERNAL_API,
            "provider": provider,
            "model": model,
            "requires_approval": True,
            "requires_payment": True,
            "rationale": f"external API ({provider}:{model}) for {tier} — user-approved paid path"
                         + ("" if _provider_key_present(provider) else " [WARNING: no API key set]"),
        }

    if prefer == TARGET_RENTED_REMOTE and allow_paid:
        model = _RENTED_REMOTE_MODELS.get(tier, "qwen2.5:14b-instruct")
        return {
            "target": TARGET_RENTED_REMOTE,
            "provider": None,
            "model": model,
            "requires_approval": True,
            "requires_payment": True,
            "rationale": f"rent remote GPU to run {model} for {tier} — user-approved paid path "
                         f"(goes through compute fabric estimate→approve→provision)",
        }

    # Default / not-allowed-paid → free local model.
    local_model = resolve_tier(tier)
    paid_available = tier in (TIER_CODE, TIER_HEAVY, TIER_DEEP)
    return {
        "target": TARGET_LOCAL,
        "provider": None,
        "model": local_model,
        "requires_approval": False,
        "requires_payment": False,
        "rationale": f"local {local_model} for {tier} (free)"
                     + ("; paid external-API or rented-GPU upgrade available on approval" if paid_available else ""),
    }


def upgrade_options(tier: str) -> list[dict]:
    """Paid upgrade options the UI can offer for a tier (always require approval+payment)."""
    opts = [resolve_target(tier, prefer=TARGET_EXTERNAL_API, allow_paid=True),
            resolve_target(tier, prefer=TARGET_RENTED_REMOTE, allow_paid=True)]
    return opts


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

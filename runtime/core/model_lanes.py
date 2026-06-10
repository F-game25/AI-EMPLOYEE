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


# ── Execution targets (local / external API / rented remote) ──────────────────
# Per requirement: CODE and heavy/deep work may also run on an EXTERNAL API
# (Claude/GPT) or on RENTED remote compute (a much bigger local model on a rented
# GPU). Both are PAID + require user approval — never auto-selected silently.

TARGET_LOCAL = "local"
TARGET_EXTERNAL_API = "external_api"   # Claude / GPT etc. — paid
TARGET_RENTED_REMOTE = "rented_remote"  # rent a GPU, run a big local model — paid

# Best external-API model per tier (env-overridable). Coder tier prefers a coding model.
_EXTERNAL_API_MODELS: dict[str, tuple[str, str]] = {
    # tier -> (provider, model)
    TIER_CODE:   ("anthropic", os.environ.get("CLAUDE_CODE_MODEL", "claude-opus-4-6")),
    TIER_DEEP:   ("anthropic", os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")),
    TIER_HEAVY:  ("anthropic", os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")),
    TIER_NORMAL: ("openai", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")),
    TIER_FAST:   ("openai", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")),
}

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
        provider, model = _EXTERNAL_API_MODELS.get(tier, ("anthropic", "claude-opus-4-6"))
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

"""Gated escalation policy for the cost-first compute ladder.

Turns a ``ComputePlan`` (from ``engine.compute.compute_planner``) into the concrete
route to execute. The whole point is **deny-by-default** for anything that leaves the
machine or spends money:

  - ``local_*``        -> the planner's local model. No egress, no spend.
  - ``openrouter_free``-> OpenRouter free tier ONLY when ALL hold: ``MODEL_ALLOW_OPENROUTER_OVERFLOW``
                          is set, privacy mode permits external APIs, not offline, and a key is
                          present. Otherwise -> silent-safe local fallback (never silent egress).
  - ``rent_gpu``       -> emits a non-blocking HITL approval card (compute-fabric flow). NEVER
                          provisions or charges here; the run proceeds on the local fallback.

This module computes the route + raises the approval + reports observability. It does NOT
own the per-run contextvar lifecycle - the caller wraps execution in
``run_model_context.preferred_model_scope(route.model, route.provider)`` so the hint is
always reset. Reuses ``model_lanes.resolve_target`` (rented target) and ``hitl_gate``.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass

logger = logging.getLogger("core.model_escalation")

# Default-OFF master switch for free cloud overflow. Real egress is impossible unless set.
_OVERFLOW_FLAG = "MODEL_ALLOW_OPENROUTER_OVERFLOW"
# Free OpenRouter model used for overflow (env-overridable; documented default).
_OPENROUTER_FREE_MODEL_DEFAULT = "meta-llama/llama-3.1-8b-instruct:free"


@dataclass
class ResolvedRoute:
    strategy: str
    model: str
    provider: str | None        # None = local Ollama; 'openrouter' = gated free overflow
    external: bool              # True if this route leaves the machine
    cost_estimate_usd: float
    approval_request_id: str | None
    rationale: str

    def to_event(self) -> dict:
        d = asdict(self)
        d["egress"] = self.external
        return d


def _truthy(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes", "on")


def _offline() -> bool:
    if _truthy("TURBO_OFFLINE"):
        return True
    # Honour a runtime-toggled offline mode if turbo_quant is already loaded (cheap, no new import cost
    # because we only read it when the module is present in sys.modules).
    import sys
    mod = sys.modules.get("turbo_quant") or sys.modules.get("agents.turbo-quant.turbo_quant")
    try:
        return bool(mod.is_offline_mode()) if mod and hasattr(mod, "is_offline_mode") else False
    except Exception:  # noqa: BLE001
        return False


def _external_egress_allowed() -> tuple[bool, str]:
    """Deny-by-default gate for sending prompts to a third-party model. Fails CLOSED."""
    if not _truthy(_OVERFLOW_FLAG):
        return False, f"{_OVERFLOW_FLAG} not set"
    if _offline():
        return False, "offline mode"
    try:
        from neural_brain.config.privacy_mode import can_use_external_apis
        if not can_use_external_apis():
            return False, "privacy mode blocks external APIs"
    except Exception as exc:  # noqa: BLE001 - fail closed if the gate can't be evaluated
        return False, f"privacy gate unavailable ({exc})"
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return False, "OPENROUTER_API_KEY not set"
    return True, "allowed"


def _openrouter_free_model() -> str:
    return os.environ.get("OPENROUTER_FREE_MODEL", _OPENROUTER_FREE_MODEL_DEFAULT).strip() \
        or _OPENROUTER_FREE_MODEL_DEFAULT


def _request_rent_approval(plan, agent: str, submitted_by: str) -> tuple[str, str | None]:
    """Resolve the rented model + raise a non-blocking HITL approval. Returns (rented_model, request_id)."""
    rented_model = plan.model
    try:
        from core.model_lanes import resolve_target
        tgt = resolve_target((plan.tier or "HEAVY"), prefer="rented_remote", allow_paid=True)
        rented_model = tgt.get("model") or plan.model
    except Exception as exc:  # noqa: BLE001
        logger.debug("rent_gpu: resolve_target failed: %s", exc)

    request_id = None
    try:
        from core.hitl_gate import get_hitl_gate
        res = get_hitl_gate().require_approval(
            agent=agent,
            action=f"Rent remote GPU to run {rented_model} (est ${plan.estimated_cost_usd:.2f})",
            payload={
                "kind": "rent_compute",
                "rented_model": rented_model,
                "tier": plan.tier,
                "estimated_cost_usd": plan.estimated_cost_usd,
                "fabric_endpoint": "/api/compute/request-approval",
                "note": ("Dry-run by default. Real provisioning needs COMPUTE_FABRIC_LIVE=1 "
                         "+ a valid owner token + budget caps - no charge is possible here."),
            },
            submitted_by=submitted_by,
            blocking=False,
        )
        request_id = res.get("request_id")
    except Exception as exc:  # noqa: BLE001 - approval is best-effort; the run still proceeds locally
        logger.warning("rent_gpu HITL request failed (non-fatal): %s", exc)
    return rented_model, request_id


def apply_compute_plan(plan, *, broadcast_fn=None, agent: str = "compute-planner",
                       submitted_by: str = "system") -> ResolvedRoute:
    """Resolve a ComputePlan into a concrete, gated route. Never egresses/spends by default."""
    strategy = getattr(plan, "strategy", "local_general")
    local_model = getattr(plan, "model", "") or os.environ.get("OLLAMA_MODEL", "llama3.2")

    # Default: run locally.
    route = ResolvedRoute(strategy=strategy, model=local_model, provider=None, external=False,
                          cost_estimate_usd=0.0, approval_request_id=None,
                          rationale=getattr(plan, "rationale", ""))

    if strategy == "openrouter_free":
        allowed, reason = _external_egress_allowed()
        if allowed:
            route.provider = "openrouter"
            route.model = _openrouter_free_model()
            route.external = True
            route.rationale = f"local saturated -> OpenRouter free overflow ({route.model})"
            logger.info("escalation: openrouter_free ALLOWED -> %s", route.model)
        else:
            route.rationale = f"overflow blocked ({reason}) -> local fallback {local_model}"
            logger.info("escalation: openrouter_free BLOCKED (%s) -> local %s", reason, local_model)

    elif strategy == "rent_gpu":
        rented_model, request_id = _request_rent_approval(plan, agent, submitted_by)
        route.cost_estimate_usd = float(getattr(plan, "estimated_cost_usd", 0.0) or 0.0)
        route.approval_request_id = request_id
        route.rationale = (f"rent_gpu ({rented_model}) pending approval"
                           + (f" req={request_id}" if request_id else "")
                           + f"; running {local_model} locally meanwhile")
        logger.info("escalation: rent_gpu -> HITL request=%s, running %s locally", request_id, local_model)

    if broadcast_fn is not None:
        try:
            broadcast_fn("task:compute_plan_executed", route.to_event())
        except Exception as exc:  # noqa: BLE001
            logger.debug("broadcast compute_plan_executed failed: %s", exc)

    return route

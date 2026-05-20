"""Autonomy guardrail enforcement HTTP routes.

Endpoints for:
- Spawn limit enforcement (per-tenant and per-agent)
- Trust tier policy management
- Rate limiting (cognitive decisions)
- Budget enforcement
- Event storm detection and suppression
- Escalation gate (HITL routing)
- Violation tracking
"""
import logging
from fastapi import APIRouter, Request, HTTPException, status

from .spawn_limiter import get_spawn_limiter, get_state as spawn_state
from .trust_tier_policy import list_tiers, set_tier, get_trust_policy
from .schema import TrustTier
from .escalation_gate import list_violations, should_escalate
from .event_storm_detector import get_suppressions
from .rate_governor import get_state as rate_state
from .budget_enforcer import check_budget, enforce as enforce_budget

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cognitive/guardrails", tags=["cognitive"])


def _tenant(req: Request) -> str:
    """Extract tenant_id from request state or headers."""
    tenant = getattr(req.state, "tenant_id", None)
    return tenant or req.headers.get("X-Tenant-Id", "system")


@router.get("/status", summary="Get guardrail status")
async def guardrail_status(req: Request):
    """Get full guardrail status: spawn limits, suppressions, rate state."""
    try:
        return {
            "spawn_state": spawn_state(),
            "suppressions": get_suppressions(),
            "rate_state": rate_state(),
        }
    except Exception as e:
        logger.error(f"Guardrail status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get guardrail status")


@router.get("/violations", summary="List guardrail violations")
async def get_violations(req: Request, limit: int = 50):
    """List guardrail violations for tenant."""
    try:
        violations = list_violations(_tenant(req), limit)
        return {"violations": violations, "count": len(violations)}
    except Exception as e:
        logger.error(f"List violations error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list violations")


@router.get("/trust-tiers", summary="List trust tiers")
async def get_trust_tiers(req: Request):
    """Get trust tier assignments for all agents in tenant."""
    try:
        tiers = list_tiers(_tenant(req))
        return {"tiers": tiers}
    except Exception as e:
        logger.error(f"List trust tiers error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list trust tiers")


@router.post("/trust-tiers/{agent_id}", summary="Set agent trust tier")
async def set_agent_trust_tier(agent_id: str, req: Request):
    """Set trust tier for agent (supervised, assisted, autonomous, trusted)."""
    try:
        body = await req.json()
        tier_val = body.get("tier", "autonomous")
        try:
            tier = TrustTier(tier_val)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {tier_val}")

        set_tier(agent_id, tier, _tenant(req))
        logger.info(f"Trust tier set: {agent_id} -> {tier.value} in tenant {_tenant(req)}")
        return {"ok": True, "agent_id": agent_id, "tier": tier.value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set trust tier error: {e}")
        raise HTTPException(status_code=500, detail="Failed to set trust tier")


@router.get("/spawn-state", summary="Get spawn limit state")
async def get_spawn_state(req: Request):
    """Get current spawn counts per tenant and per agent."""
    try:
        return spawn_state()
    except Exception as e:
        logger.error(f"Get spawn state error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get spawn state")


@router.post("/reset/{agent_id}", summary="Reset agent spawn count")
async def reset_agent(agent_id: str, req: Request):
    """Reset spawn count for agent in tenant (clears deadlock)."""
    try:
        await get_spawn_limiter().reset_agent(_tenant(req), agent_id)
        logger.info(f"Agent spawn reset: {agent_id} in tenant {_tenant(req)}")
        return {"ok": True, "agent_id": agent_id}
    except Exception as e:
        logger.error(f"Reset agent error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset agent")


@router.get("/budget", summary="Check budget status")
async def get_budget_status(req: Request):
    """Check token budget against daily limit."""
    try:
        status_dict = check_budget(_tenant(req))
        return status_dict
    except Exception as e:
        logger.error(f"Check budget error: {e}")
        raise HTTPException(status_code=500, detail="Failed to check budget")


@router.post("/check-escalation/{agent_id}", summary="Check if action requires escalation")
async def check_escalation(agent_id: str, req: Request):
    """Check if agent action should be escalated to HITL."""
    try:
        body = await req.json()
        action_type = body.get("action_type", "unknown")
        escalate = should_escalate(agent_id, action_type, _tenant(req))
        return {
            "ok": True,
            "agent_id": agent_id,
            "action_type": action_type,
            "requires_escalation": escalate,
        }
    except Exception as e:
        logger.error(f"Check escalation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to check escalation")


@router.get("/suppressions", summary="Get event storm suppressions")
async def get_event_suppressions(req: Request):
    """Get currently suppressed event channels and remaining suppression time."""
    try:
        suppressions = get_suppressions()
        return {"suppressions": suppressions}
    except Exception as e:
        logger.error(f"Get suppressions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get suppressions")

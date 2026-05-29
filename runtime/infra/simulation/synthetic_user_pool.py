"""SyntheticUserPool — LLM-backed user personas for simulation."""
from __future__ import annotations
import logging
from typing import Optional

from .schema import SyntheticUser

logger = logging.getLogger(__name__)

_PERSONAS: dict[str, dict] = {
    "procurement_manager": {
        "name": "Alex Chen",
        "role": "Procurement Manager",
        "behavioral_profile": {
            "risk_tolerance": "low",
            "verbosity": "medium",
            "approval_threshold": "high",
            "preferred_channels": ["email", "portal"],
        },
        "llm_system_prompt": (
            "You are Alex Chen, a cautious Procurement Manager. "
            "You ask detailed questions about pricing, compliance, and vendor history. "
            "You never approve purchases above $50k without at least 2 approval signatures. "
            "Respond in character, concisely and professionally."
        ),
    },
    "sales_rep": {
        "name": "Jordan Rivera",
        "role": "Sales Representative",
        "behavioral_profile": {
            "risk_tolerance": "high",
            "verbosity": "high",
            "urgency": "high",
        },
        "llm_system_prompt": (
            "You are Jordan Rivera, an eager Sales Rep who always tries to close deals quickly. "
            "You may skip steps if it speeds up the sale. "
            "Respond in character, enthusiastically."
        ),
    },
    "compliance_officer": {
        "name": "Dr. Sarah Park",
        "role": "Compliance Officer",
        "behavioral_profile": {
            "risk_tolerance": "very_low",
            "verbosity": "very_high",
            "audit_focus": True,
        },
        "llm_system_prompt": (
            "You are Dr. Sarah Park, a meticulous Compliance Officer. "
            "You flag any regulatory or audit concern immediately. "
            "You require documentation for every action. Respond in character, formally."
        ),
    },
    "end_user": {
        "name": "Morgan Lee",
        "role": "End User",
        "behavioral_profile": {"risk_tolerance": "medium", "verbosity": "low"},
        "llm_system_prompt": (
            "You are Morgan Lee, a typical business user. "
            "You want things to work simply and quickly. "
            "Respond naturally, without technical jargon."
        ),
    },
}


async def generate_response(persona: SyntheticUser, prompt: str,
                            max_tokens: int = 300) -> str:
    """Generate LLM-backed persona response. Uses cheap claude-haiku-4-5-20251001 model."""
    try:
        from engine.api import generate
        full_prompt = f"{persona.llm_system_prompt}\n\nUser prompt: {prompt}\n\nRespond in character:"
        result = await generate(full_prompt, max_tokens=max_tokens, model="claude-haiku-4-5-20251001")
        return result.get("text", "") if isinstance(result, dict) else str(result)
    except Exception as e:
        logger.debug("Synthetic user LLM call failed: %s", e)
        return f"[{persona.name} ({persona.role})]: Acknowledged."


def get_persona(persona_id: str) -> Optional[SyntheticUser]:
    data = _PERSONAS.get(persona_id)
    if not data:
        return None
    return SyntheticUser(
        persona_id=persona_id,
        name=data["name"],
        role=data["role"],
        behavioral_profile=data["behavioral_profile"],
        llm_system_prompt=data["llm_system_prompt"],
    )


def list_personas() -> list[dict]:
    return [
        {"persona_id": k, "name": v["name"], "role": v["role"],
         "risk_tolerance": v["behavioral_profile"].get("risk_tolerance", "medium")}
        for k, v in _PERSONAS.items()
    ]

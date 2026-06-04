"""Step-level confidence scoring."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.quantum.candidate import Candidate
from core.quantum.search.schema import ContextPack

STEP_WEIGHTS = {
    'tool_past_success':   0.25,
    'action_base_risk':    0.20,
    'agent_trust_score':   0.15,
    'context_coverage':    0.15,
    'prior_step_success':  0.10,
    'sandbox_available':   0.08,
    'tenant_permission':   0.07,
}

RISK_MAP = {
    'read_file': 0.0,  'search_web': 0.0,  'get_memory': 0.0,
    'write_file': 0.2, 'create_file': 0.2, 'update_db': 0.2,
    'run_code': 0.4,   'run_shell': 0.4,
    'send_email': 0.6, 'call_api': 0.6, 'browse_url': 0.5, 'post_social': 0.6,
    'pay_invoice': 0.8, 'transfer_funds': 0.9, 'publish_public': 0.7,
    'rm_rf': 1.0,       'drop_table': 1.0, 'delete_all': 1.0,
}


@dataclass
class StepScore:
    confidence: float
    risk_penalty: float
    tool_amplitude: float
    gate: str    # 'direct' | 'sandbox' | 'hitl' | 'reject'
    breakdown: dict = field(default_factory=dict)


def _lookup_candidate(context_pack: ContextPack, id_val: str, attr: str, default: float) -> float:
    if not id_val:
        return default
    for c in context_pack.candidates:
        if isinstance(c, Candidate) and c.result.id == id_val:
            return getattr(c.result, attr, default)
    return default


def score_step(
    step: dict,
    context_pack: ContextPack,
    prior_success: float = 0.5,
    sandbox_available: bool = True,
    tenant_permission: float = 1.0,
) -> StepScore:
    action   = step.get('action', '')
    tool_id  = step.get('tool_id', '')
    agent_id = step.get('agent_id', '')

    risk       = RISK_MAP.get(action, 0.3)
    tool_amp   = _lookup_candidate(context_pack, tool_id, 'amplitude', 0.5) if tool_id else 0.5

    signals = {
        'tool_past_success':  _lookup_candidate(context_pack, tool_id,  'past_success_rate', 0.5),
        'action_base_risk':   1.0 - risk,
        'agent_trust_score':  _lookup_candidate(context_pack, agent_id, 'past_success_rate', 0.5),
        'context_coverage':   context_pack.confidence,
        'prior_step_success': prior_success,
        'sandbox_available':  1.0 if sandbox_available else 0.0,
        'tenant_permission':  tenant_permission,
    }

    confidence = sum(STEP_WEIGHTS[k] * signals[k] for k in STEP_WEIGHTS)
    confidence = round(min(max(confidence, 0.0), 1.0), 4)

    if confidence > 0.85:
        gate = 'direct'
    elif confidence > 0.60:
        gate = 'sandbox'
    elif confidence > 0.40:
        gate = 'hitl'
    else:
        gate = 'reject'

    return StepScore(
        confidence=confidence,
        risk_penalty=risk,
        tool_amplitude=tool_amp,
        gate=gate,
        breakdown=signals,
    )

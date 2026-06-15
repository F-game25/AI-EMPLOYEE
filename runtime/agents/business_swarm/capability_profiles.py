"""Derive AgentContracts from the REAL catalog (runtime/config/agent_capabilities.json).

Contracts are NOT invented — each is mapped from a live catalog entry. Risk level,
tool permissions, memory scope, output contract and requires_approval_for are derived
deterministically from the agent's category + skills/specialties, so the governance
posture is honest and consistent with what the agent actually does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .agent_contracts import (
    ACTION_DATA_WRITE,
    ACTION_DEPLOY,
    ACTION_HIRE,
    ACTION_OUTREACH,
    ACTION_PUBLISH,
    ACTION_SCAN,
    ACTION_SEND_EMAIL,
    ACTION_SPEND,
    ACTION_TRADE,
    AgentContract,
    RISK_L0,
    RISK_L1,
    RISK_L2,
    RISK_L3,
    RISK_L4,
)


def _catalog_path() -> Path:
    """Locate agent_capabilities.json without hardcoding an absolute path."""
    env = os.environ.get("AGENT_CAPABILITIES_PATH")
    if env and Path(env).is_file():
        return Path(env)
    # business_swarm/ -> agents/ -> runtime/ -> repo root
    here = Path(__file__).resolve()
    runtime_root = here.parents[2]
    candidate = runtime_root / "config" / "agent_capabilities.json"
    if candidate.is_file():
        return candidate
    # Fallback: walk up to a repo root containing runtime/config/.
    for parent in here.parents:
        c = parent / "runtime" / "config" / "agent_capabilities.json"
        if c.is_file():
            return c
    raise FileNotFoundError("agent_capabilities.json not found (set AGENT_CAPABILITIES_PATH)")


def _load_catalog() -> dict[str, Any]:
    with open(_catalog_path(), "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("agents", {}) if isinstance(data, dict) else {}


# ── Derivation rules (category-driven; honest defaults) ───────────────────────

# Categories whose core job is consequential external/world-changing action.
_CONSEQUENTIAL_ACTIONS_BY_CATEGORY: dict[str, list[str]] = {
    "sales": [ACTION_OUTREACH, ACTION_SEND_EMAIL],
    "social": [ACTION_PUBLISH, ACTION_OUTREACH],
    "content": [ACTION_PUBLISH],
    "creative": [ACTION_PUBLISH],
    "marketing": [ACTION_PUBLISH, ACTION_SPEND],
    "growth": [ACTION_PUBLISH, ACTION_SPEND],
    "ecommerce": [ACTION_PUBLISH, ACTION_SPEND, ACTION_DATA_WRITE],
    "trading": [ACTION_TRADE, ACTION_SPEND],
    "crypto": [ACTION_TRADE, ACTION_PUBLISH],
    "finance": [ACTION_SPEND],
    "intelligence": [ACTION_SCAN],
    "communication": [ACTION_SEND_EMAIL, ACTION_OUTREACH],
    "development": [ACTION_DEPLOY],
    "engineering": [ACTION_DEPLOY],
    "coding": [ACTION_DEPLOY],
    "hr": [ACTION_HIRE, ACTION_OUTREACH],
}

# Keyword → action signals from skills/specialties (catches cross-category cases).
_ACTION_KEYWORDS: dict[str, list[str]] = {
    ACTION_PUBLISH: ["publish", "post", "scheduling", "schedule", "posting"],
    ACTION_OUTREACH: ["outreach", "cold_email", "cold email", "prospect", "dms", "connection"],
    ACTION_SEND_EMAIL: ["send", "mailchimp", "smtp", "campaign", "deliverability"],
    ACTION_SPEND: ["budget", "ad", "ads", "spend", "paid"],
    ACTION_TRADE: ["trade", "trading", "signal", "portfolio", "order"],
    ACTION_DEPLOY: ["deploy", "patch", "apply", "shell_exec", "code_exec", "rollout"],
    ACTION_SCAN: ["scan", "recon", "osint", "exploit"],
    ACTION_DATA_WRITE: ["reorder", "publish", "fulfil", "fulfill", "inventory_update"],
    ACTION_HIRE: ["hire", "candidate", "recruit", "onboarding"],
}

# Low-risk read/analysis categories.
_ANALYST_CATEGORIES = {"analytics", "research", "strategy", "design", "testing"}

# Infra/coordination = orchestration, no direct world-changing action.
_COORDINATION_CATEGORIES = {
    "coordination",
    "orchestrator",
    "operations",
    "management",
    "infrastructure",
}

_BASE_TOOLS = ["llm.generate", "memory.search"]
_ANALYST_TOOLS = ["web.search", "data.read"]
_WRITER_TOOLS = ["draft.write"]

_ACTION_TOOLS: dict[str, str] = {
    ACTION_PUBLISH: "publish.queue",
    ACTION_OUTREACH: "outreach.queue",
    ACTION_SEND_EMAIL: "email.send",
    ACTION_SPEND: "budget.allocate",
    ACTION_TRADE: "trade.execute",
    ACTION_DEPLOY: "deploy.apply",
    ACTION_SCAN: "security.scan",
    ACTION_DATA_WRITE: "state.write",
    ACTION_HIRE: "hr.action",
}


def _signal_text(meta: dict[str, Any]) -> str:
    parts = list(meta.get("skills") or []) + list(meta.get("specialties") or [])
    parts.append(meta.get("description", ""))
    return " ".join(str(p).lower() for p in parts)


def _derive_actions(category: str, meta: dict[str, Any]) -> list[str]:
    actions: list[str] = list(_CONSEQUENTIAL_ACTIONS_BY_CATEGORY.get(category, []))
    text = _signal_text(meta)
    for action, keywords in _ACTION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            actions.append(action)
    # Stable, de-duplicated order.
    seen: list[str] = []
    for a in actions:
        if a not in seen:
            seen.append(a)
    return seen


def _derive_risk(category: str, actions: list[str]) -> str:
    if ACTION_TRADE in actions or ACTION_SPEND in actions:
        return RISK_L4
    if category == "intelligence" or ACTION_SCAN in actions:
        return RISK_L4
    if ACTION_DEPLOY in actions:
        return RISK_L3
    if {ACTION_PUBLISH, ACTION_OUTREACH, ACTION_SEND_EMAIL, ACTION_HIRE} & set(actions):
        return RISK_L3
    if ACTION_DATA_WRITE in actions:
        return RISK_L2
    if category in _ANALYST_CATEGORIES:
        return RISK_L0
    if category in _COORDINATION_CATEGORIES:
        return RISK_L1
    return RISK_L1


def _derive_output_contract(category: str, actions: list[str]) -> str:
    if category in _ANALYST_CATEGORIES:
        return "analysis"
    if category == "finance":
        return "advisory"
    if category in ("development", "engineering", "coding"):
        return "code_change"
    if category in ("content", "creative", "social", "marketing", "sales", "communication"):
        return "draft"
    if category in _COORDINATION_CATEGORIES:
        return "structured_report"
    return "analysis"


def _derive_tools(category: str, actions: list[str]) -> list[str]:
    tools = list(_BASE_TOOLS)
    if category in _ANALYST_CATEGORIES or category == "research":
        tools += _ANALYST_TOOLS
    tools += _WRITER_TOOLS
    for action in actions:
        tool = _ACTION_TOOLS.get(action)
        if tool and tool not in tools:
            tools.append(tool)
    return tools


def _derive_memory_scope(agent_id: str, category: str) -> list[str]:
    scope = [f"agent:{agent_id}", f"category:{category}", "project:shared"]
    if category in _ANALYST_CATEGORIES or category == "research":
        scope.append("knowledge:read")
    return scope


def _derive_success_metrics(category: str, output_contract: str) -> list[str]:
    base = ["output_completeness", "schema_valid", "human_review_pass_rate"]
    if output_contract == "analysis":
        return ["evidence_coverage", "source_attribution"] + base
    if output_contract == "draft":
        return ["on_brand_score", "edit_distance_to_approved"] + base
    if output_contract == "advisory":
        return ["assumption_transparency", "human_signoff_rate"] + base
    if output_contract == "code_change":
        return ["tests_pass", "review_pass", "rollback_available"] + base
    return base


def _derive_escalation(risk: str, actions: list[str]) -> list[str]:
    rules: list[str] = ["on_error:return_status_unavailable_no_fabrication"]
    if actions:
        rules.append("on_consequential_action:route_to_hitl_approval")
    if risk in (RISK_L3, RISK_L4):
        rules.append("on_low_confidence:escalate_to_human")
    if risk == RISK_L4:
        rules.append("on_financial_or_security_impact:require_strict_signoff")
    return rules


def build_contracts() -> dict[str, AgentContract]:
    """Map every catalog agent to an AgentContract. Returns {id: AgentContract}."""
    catalog = _load_catalog()
    contracts: dict[str, AgentContract] = {}
    for agent_id, meta in catalog.items():
        if not isinstance(meta, dict):
            continue
        category = str(meta.get("category", "general")).lower()
        capabilities = list(meta.get("skills") or [])
        role = str(meta.get("description") or agent_id).split(" — ")[0].strip() or agent_id

        actions = _derive_actions(category, meta)
        risk = _derive_risk(category, actions)
        output_contract = _derive_output_contract(category, actions)

        contracts[agent_id] = AgentContract(
            id=agent_id,
            role=role,
            capabilities=capabilities,
            tools_allowed=_derive_tools(category, actions),
            memory_scope=_derive_memory_scope(agent_id, category),
            risk_level=risk,
            requires_approval_for=actions,
            output_contract=output_contract,
            success_metrics=_derive_success_metrics(category, output_contract),
            escalation_rules=_derive_escalation(risk, actions),
            category=category,
            model=meta.get("model"),
        )
    return contracts

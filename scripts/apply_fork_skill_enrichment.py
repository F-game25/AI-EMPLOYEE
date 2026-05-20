#!/usr/bin/env python3
"""Merge fork-derived capabilities into the global skills library.

This script is intentionally idempotent: it replaces only skills marked with
the AETERNUS fork source packs and leaves all existing user/system skills alone.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILLS_FILE = ROOT / "runtime" / "config" / "skills_library.json"
FORK_FILE = ROOT / "runtime" / "config" / "fork_integration_manifest.json"

SOURCE_BY_PACK = {
    "agent-skills": {
        "source_url": "https://github.com/addyosmani/agent-skills",
        "source_commit": "f17c6e88c904dc747381c374312c2d58e10647ae",
        "license": "MIT",
    },
    "financial-services": {
        "source_url": "https://github.com/anthropics/financial-services",
        "source_commit": "853f755a61f7bbb045c681327f46b354419030a1",
        "license": "Apache-2.0",
    },
    "cashclaw": {
        "source_url": "https://github.com/moltlaunch/cashclaw",
        "source_commit": "fb5974ec0f3840ecdd973d20cd74a0735f62289c",
        "license": "MIT",
    },
    "automaton": {
        "source_url": "https://github.com/Conway-Research/automaton",
        "source_commit": "22096f78f20bef63660e24a433f290769af6290f",
        "license": "MIT",
    },
    "wallet-vault": {
        "source_url": "internal:aeternus-wallet-vault",
        "source_commit": "local-policy",
        "license": "AETERNUS-INTERNAL",
    },
    "openclaw": {
        "source_url": "https://github.com/openclaw/openclaw",
        "source_commit": "c8d9733e41bdd59d5e1e454d75e31abb655fc430",
        "license": "MIT",
    },
}

SOURCE_PACKS = set(SOURCE_BY_PACK)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def snake(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", value).strip("_")


def base_skill(
    *,
    skill_id: str,
    name: str,
    category: str,
    description: str,
    source_pack: str,
    aliases: list[str],
    tags: list[str],
    compatible_agents: list[str],
    risk_level: str,
    approval_policy: str,
    execution_steps: list[str],
    verification_gates: list[str],
    system_prompt: str,
) -> dict[str, Any]:
    source = SOURCE_BY_PACK[source_pack]
    return {
        "id": skill_id,
        "name": name,
        "category": category,
        "description": description,
        "prompt_hint": f"Use {name} for [goal]. Return a plan, execution constraints, verification gates, and approval needs.",
        "tags": sorted(set(tags + [source_pack, "aeternus-native"])),
        "aliases": aliases,
        "compatible_agents": compatible_agents,
        "source_pack": source_pack,
        "source_url": source["source_url"],
        "source_commit": source["source_commit"],
        "license": source["license"],
        "risk_level": risk_level,
        "approval_policy": approval_policy,
        "input_format": {
            "required_fields": ["task_goal", "context", "constraints"],
            "optional_fields": ["files", "examples", "risk", "deadline", "owner_approval"],
            "input_contract": "Reject empty goals. Preserve offline-first policy. Surface missing context before action.",
        },
        "output_format": {
            "sections": ["result", "rationale", "verification", "approval_requirements", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Outputs must separate draft work from approved execution and include verification status.",
        },
        "quality_standards": [
            "Use existing AETERNUS architecture and do not create a replacement subsystem.",
            "State assumptions, risks, and approval gates explicitly.",
            "Prefer reversible, testable, incremental work.",
            "Never bypass security, auth, sandboxing, policy, or audit logging.",
        ],
        "error_handling": {
            "retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"],
            "non_retryable_errors": ["missing_owner_approval", "forbidden_policy_action", "invalid_contract"],
            "fallback_strategy": "Return a degraded result with explicit missing prerequisites and no external side effects.",
        },
        "best_practices": [
            "Use native AETERNUS APIs and manifests.",
            "Keep generated outputs staged until reviewed.",
            "Write audit events for policy-relevant work.",
            "Attach verification commands or acceptance criteria.",
        ],
        "execution_steps": execution_steps,
        "verification_gates": verification_gates,
        "system_prompt": system_prompt,
    }


def engineering_skills(fork: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for item in fork.get("engineering_skills", []):
        canonical = f"agent_skill_{snake(item['id'])}"
        gates = item.get("verification_gates") or ["acceptance criteria", "tests pass", "review"]
        skills.append(base_skill(
            skill_id=canonical,
            name=f"Agent Skill: {item['name']}",
            category="AETERNUS Engineering Skills",
            description=f"Native engineering workflow skill converted from agent-skills: {item['name']}.",
            source_pack="agent-skills",
            aliases=[item["id"]],
            tags=["engineering", item.get("category", "workflow"), *item.get("trigger_keywords", [])],
            compatible_agents=["ascend-forge", "task-orchestrator", "bot-dev", "project-manager"],
            risk_level="caution" if item.get("category") in {"security", "automation", "release"} else "safe",
            approval_policy="policy_check_required_for_execution",
            execution_steps=[
                "Classify the requested build/change goal.",
                "Apply the skill workflow to produce a staged plan.",
                "Attach verification gates and approval requirements.",
                "Hand execution to AscendForge or Task Orchestrator under policy control.",
            ],
            verification_gates=gates,
            system_prompt=f"You are applying the {item['name']} workflow inside AETERNUS NEXUS. Enhance existing systems, preserve architecture, and return actionable gates.",
        ))
    return skills


def finance_skills(fork: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for item in fork.get("finance_workflows", []):
        canonical = f"finance_workflow_{snake(item['id'])}"
        skills.append(base_skill(
            skill_id=canonical,
            name=f"Finance Workflow: {item['name']}",
            category="Supervised Finance Workflows",
            description=f"Draft-only supervised finance workflow for {item.get('domain', 'finance')} work.",
            source_pack="financial-services",
            aliases=[item["id"], item.get("agent", "")],
            tags=["finance", "draft", item.get("domain", "finance")],
            compatible_agents=["finance-wizard", "task-orchestrator", "ascend-forge"],
            risk_level="dangerous",
            approval_policy="draft_only_human_review_required_no_transactions",
            execution_steps=[
                "Collect source documents and assumptions.",
                "Create a draft analysis or workflow output.",
                "Flag missing sources, assumptions, and compliance concerns.",
                "Block export, ledger posting, trading, or external use until human approval.",
            ],
            verification_gates=["source coverage", "assumption review", "human approval", "no transaction execution"],
            system_prompt="You are a supervised finance workflow agent. Produce draft analysis only. Do not give investment advice, post ledgers, execute trades, or move funds.",
        ))
    return skills


def fixed_skills() -> list[dict[str, Any]]:
    money_specs = [
        ("money_task_discovery", "Money Task Discovery", "Find internal or approved external earning opportunities.", "safe"),
        ("money_task_evaluation", "Money Task Evaluation", "Evaluate fit, risk, scope, and expected value for a task.", "caution"),
        ("money_quote_drafting", "Money Quote Drafting", "Draft price and delivery quote for owner review.", "caution"),
        ("money_delivery_approval", "Money Delivery Approval", "Stage deliverables and block external delivery until approval.", "dangerous"),
        ("money_feedback_ingestion", "Money Feedback Ingestion", "Convert client/task feedback into memory and improvement notes.", "safe"),
        ("money_earnings_lifecycle", "Money Earnings Lifecycle", "Track pending, available, claimed, and reinvested earnings.", "dangerous"),
    ]
    autonomy_specs = [
        ("autonomy_policy_evaluation", "Autonomy Policy Evaluation", "Evaluate actions against safe/caution/dangerous/forbidden policy.", "caution"),
        ("autonomy_tool_risk_classification", "Autonomy Tool Risk Classification", "Classify tool calls before execution.", "caution"),
        ("autonomy_heartbeat_monitoring", "Autonomy Heartbeat Monitoring", "Monitor long-running agent loops and heartbeat state.", "safe"),
        ("autonomy_loop_detection", "Autonomy Loop Detection", "Detect repeated ineffective action loops.", "caution"),
        ("autonomy_self_modification_audit", "Autonomy Self Modification Audit", "Audit proposed self-modification before approval.", "dangerous"),
        ("autonomy_approval_gate", "Autonomy Approval Gate", "Require human approval for dangerous actions.", "dangerous"),
    ]
    wallet_specs = [
        ("wallet_owner_vault_setup", "Owner Wallet Vault Setup", "Create an encrypted owner-controlled local wallet vault.", "dangerous"),
        ("wallet_claim_request", "Wallet Claim Request", "Prepare owner claim requests for earned funds.", "dangerous"),
        ("wallet_compute_quote", "External Compute Quote", "Draft external compute purchase quotes without executing purchase.", "dangerous"),
        ("wallet_spend_approval", "Wallet Spend Approval", "Require owner approval and limits before any spend.", "dangerous"),
    ]
    channel_specs = [
        ("channel_local_pairing", "Local Channel Pairing", "Pair local dashboard/mobile sessions with explicit approval.", "caution"),
        ("channel_allowlist_routing", "Channel Allowlist Routing", "Route messages only from allowed channels/senders.", "caution"),
        ("channel_session_routing", "Channel Session Routing", "Route channel sessions to assigned agents.", "safe"),
    ]

    out: list[dict[str, Any]] = []
    for sid, name, desc, risk in money_specs:
        out.append(base_skill(
            skill_id=sid,
            name=name,
            category="Money Mode",
            description=desc,
            source_pack="cashclaw",
            aliases=[sid.replace("_", "-")],
            tags=["money-mode", "task-lifecycle"],
            compatible_agents=["task-orchestrator", "ascend-forge", "finance-wizard"],
            risk_level=risk,
            approval_policy="owner_approval_required_for_external_delivery_or_money_movement",
            execution_steps=["Load task context.", "Evaluate lifecycle state.", "Create staged result.", "Request approval for external or money actions."],
            verification_gates=["task state recorded", "approval gate respected", "memory feedback path"],
            system_prompt="You are enhancing Money Mode. Prepare and stage work, but never deliver externally or move money without owner approval.",
        ))
    for sid, name, desc, risk in autonomy_specs:
        out.append(base_skill(
            skill_id=sid,
            name=name,
            category="Autonomy Governance",
            description=desc,
            source_pack="automaton",
            aliases=[sid.replace("_", "-")],
            tags=["autonomy", "policy", "audit"],
            compatible_agents=["ascend-forge", "task-orchestrator", "blacklight-security"],
            risk_level=risk,
            approval_policy="policy_decision_required_before_action",
            execution_steps=["Normalize requested action.", "Classify risk.", "Apply policy decision.", "Record audit requirement."],
            verification_gates=["risk classified", "forbidden blocked", "dangerous approval required"],
            system_prompt="You are the AETERNUS autonomy policy layer. Classify actions and enforce approval without bypass.",
        ))
    for sid, name, desc, risk in wallet_specs:
        out.append(base_skill(
            skill_id=sid,
            name=name,
            category="Wallet & Compute",
            description=desc,
            source_pack="wallet-vault",
            aliases=[sid.replace("_", "-")],
            tags=["wallet", "compute", "owner-approval"],
            compatible_agents=["ascend-forge", "finance-wizard", "task-orchestrator"],
            risk_level=risk,
            approval_policy="owner_approval_required_autonomous_spending_blocked",
            execution_steps=["Validate owner approval.", "Prepare local-only staged operation.", "Write audit record.", "Block autonomous spend by default."],
            verification_gates=["owner approval", "spend disabled by default", "audit record"],
            system_prompt="You manage owner-controlled wallet and compute quote workflows. Never spend or purchase autonomously.",
        ))
    for sid, name, desc, risk in channel_specs:
        out.append(base_skill(
            skill_id=sid,
            name=name,
            category="Communication Channels",
            description=desc,
            source_pack="openclaw",
            aliases=[sid.replace("_", "-")],
            tags=["channels", "mobile", "routing"],
            compatible_agents=["task-orchestrator", "ascend-forge", "support-bot"],
            risk_level=risk,
            approval_policy="pairing_and_allowlist_required",
            execution_steps=["Verify channel identity.", "Check allowlist.", "Route to assigned session.", "Audit rejected senders."],
            verification_gates=["paired channel", "allowlist match", "route recorded"],
            system_prompt="You route local/mobile communication safely through AETERNUS channel policy.",
        ))
    return out


def main() -> int:
    skills_data = load_json(SKILLS_FILE)
    fork = load_json(FORK_FILE)

    generated = engineering_skills(fork) + finance_skills(fork) + fixed_skills()
    generated_by_id = {item["id"]: item for item in generated}

    existing = [
        item for item in skills_data.get("skills", [])
        if not (isinstance(item, dict) and item.get("source_pack") in SOURCE_PACKS)
    ]
    existing_ids = {item.get("id") for item in existing if isinstance(item, dict)}
    collisions = sorted(existing_ids & set(generated_by_id))
    if collisions:
        raise SystemExit(f"Refusing to overwrite non-imported skills: {collisions}")

    skills_data["skills"] = existing + sorted(generated_by_id.values(), key=lambda item: item["id"])
    categories = list(skills_data.get("categories", []))
    for category in [
        "AETERNUS Engineering Skills",
        "Supervised Finance Workflows",
        "Money Mode",
        "Autonomy Governance",
        "Wallet & Compute",
        "Communication Channels",
    ]:
        if category not in categories:
            categories.append(category)
    skills_data["categories"] = categories
    skills_data.setdefault("_meta", {})
    skills_data["_meta"]["version"] = "3.1"
    skills_data["_meta"]["total_skills"] = len(skills_data["skills"])
    skills_data["_meta"]["updated_at"] = date.today().isoformat()
    skills_data["_meta"]["fork_enrichment"] = {
        "enabled": True,
        "imported_skill_count": len(generated_by_id),
        "source_packs": sorted(SOURCE_PACKS),
        "mode": "native_enhancement_layer",
    }
    skills_data["_meta"]["description"] = (
        f"AI Employee Skills Library - {len(skills_data['skills'])} reusable skills, "
        "including native fork-derived engineering, finance, money, autonomy, wallet, and channel skills."
    )

    canonical_by_alias = {alias: item["id"] for item in generated for alias in item.get("aliases", [])}
    for item in fork.get("engineering_skills", []):
        item["canonical_skill_id"] = canonical_by_alias.get(item["id"], f"agent_skill_{snake(item['id'])}")
    for item in fork.get("finance_workflows", []):
        item["canonical_skill_id"] = canonical_by_alias.get(item["id"], f"finance_workflow_{snake(item['id'])}")
    fork["canonical_skill_ids"] = sorted(generated_by_id)
    fork["global_skills_library"] = {
        "path": "runtime/config/skills_library.json",
        "imported_skill_count": len(generated_by_id),
        "updated_at": date.today().isoformat(),
    }

    write_json(SKILLS_FILE, skills_data)
    write_json(FORK_FILE, fork)
    print(f"[OK] merged {len(generated_by_id)} fork-derived skills into {SKILLS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

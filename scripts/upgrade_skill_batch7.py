#!/usr/bin/env python3
"""Upgrade the seventh 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "agent_memory", "id": "agent_memory_health_checker", "name": "Agent Memory Health Checker", "subcategory": "agent-runtime", "triggers": ["check agent memory health", "agent memory", "memory health"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "agent_skill_generation", "id": "skill_generation_planner", "name": "Skill Generation Planner", "subcategory": "skill-system", "triggers": ["plan skill generation", "agent skill generation", "new skill plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "ai_ml_engineering", "id": "ai_ml_implementation_reviewer", "name": "AI/ML Implementation Reviewer", "subcategory": "ai-engineering", "triggers": ["review ai ml implementation", "ai ml engineering", "model implementation review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "ai_powered_scanning", "id": "ai_scan_plan_builder", "name": "AI Scan Plan Builder", "subcategory": "ai-engineering", "triggers": ["build ai scan plan", "ai powered scanning", "scan plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "chat_task_dispatch", "id": "chat_task_dispatch_reviewer", "name": "Chat Task Dispatch Reviewer", "subcategory": "agent-runtime", "triggers": ["review chat task dispatch", "chat task dispatch", "dispatch from chat"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "chatbot_design", "id": "chatbot_flow_reviewer", "name": "Chatbot Flow Reviewer", "subcategory": "conversation-design", "triggers": ["review chatbot flow", "chatbot design", "conversation bot flow"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "context_injection", "id": "context_injection_safety_reviewer", "name": "Context Injection Safety Reviewer", "subcategory": "prompt-security", "triggers": ["review context injection safety", "context injection", "prompt context safety"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "conversation_flows", "id": "conversation_flow_designer", "name": "Conversation Flow Designer", "subcategory": "conversation-design", "triggers": ["design conversation flow", "conversation flows", "dialog flow"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "cost_optimization", "id": "infrastructure_cost_optimizer", "name": "Infrastructure Cost Optimizer", "subcategory": "runtime-cost", "triggers": ["optimize infrastructure cost", "cost optimization", "runtime cost"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "coverage_analysis", "id": "coverage_gap_analyzer", "name": "Coverage Gap Analyzer", "subcategory": "testing", "triggers": ["analyze coverage gaps", "coverage analysis", "test coverage gaps"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "devops_infrastructure", "id": "devops_infrastructure_reviewer", "name": "DevOps Infrastructure Reviewer", "subcategory": "devops", "triggers": ["review devops infrastructure", "devops infrastructure", "infra review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "python_development", "id": "python_implementation_planner", "name": "Python Implementation Planner", "subcategory": "python", "triggers": ["plan python implementation", "python development", "python build plan"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "security_audit", "id": "security_audit_planner", "name": "Security Audit Planner", "subcategory": "security", "triggers": ["plan security audit", "security audit", "audit security"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "security_testing", "id": "security_test_plan_builder", "name": "Security Test Plan Builder", "subcategory": "security", "triggers": ["build security test plan", "security testing", "security test"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "shell_exec", "id": "shell_command_execution_reviewer", "name": "Shell Command Execution Reviewer", "subcategory": "command-safety", "triggers": ["review shell command execution", "shell exec", "command execution risk"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "prompt_scanning", "id": "prompt_injection_scan_planner", "name": "Prompt Injection Scan Planner", "subcategory": "prompt-security", "triggers": ["plan prompt injection scan", "prompt scanning", "prompt injection"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "long_term_memory", "id": "long_term_memory_policy_reviewer", "name": "Long-Term Memory Policy Reviewer", "subcategory": "memory", "triggers": ["review long term memory policy", "long term memory", "memory policy"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "memory_writeback", "id": "memory_writeback_reviewer", "name": "Memory Writeback Reviewer", "subcategory": "memory", "triggers": ["review memory writeback", "memory writeback", "write memory"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "multi_stage_reasoning", "id": "multi_stage_reasoning_planner", "name": "Multi-Stage Reasoning Planner", "subcategory": "reasoning", "triggers": ["plan multi stage reasoning", "multi stage reasoning", "reasoning plan"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "task_routing", "id": "task_routing_policy_reviewer", "name": "Task Routing Policy Reviewer", "subcategory": "agent-runtime", "triggers": ["review task routing policy", "task routing", "routing policy"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "custom_agent_builder", "id": "custom_agent_spec_builder", "name": "Custom Agent Spec Builder", "subcategory": "agent-runtime", "triggers": ["build custom agent spec", "custom agent builder", "agent spec"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "skill_search", "id": "skill_search_relevance_checker", "name": "Skill Search Relevance Checker", "subcategory": "skill-system", "triggers": ["check skill search relevance", "skill search", "find relevant skills"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "skill_gap_analysis", "id": "skill_gap_prioritizer", "name": "Skill Gap Prioritizer", "subcategory": "skill-system", "triggers": ["prioritize skill gaps", "skill gap analysis", "missing skills"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "defensive_osint", "id": "defensive_osint_brief_builder", "name": "Defensive OSINT Brief Builder", "subcategory": "research-security", "triggers": ["build defensive osint brief", "defensive osint", "osint brief"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "source_synthesis", "id": "source_synthesis_reviewer", "name": "Source Synthesis Reviewer", "subcategory": "research-quality", "triggers": ["review source synthesis", "source synthesis", "source quality synthesis"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "synthesis", "id": "synthesis_quality_reviewer", "name": "Synthesis Quality Reviewer", "subcategory": "research-quality", "triggers": ["review synthesis quality", "synthesis", "analysis synthesis"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "sec_filing_analysis", "id": "sec_filing_analysis_brief_builder", "name": "SEC Filing Analysis Brief Builder", "subcategory": "finance-research", "triggers": ["build sec filing analysis brief", "sec filing analysis", "10-k analysis"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "legal_review", "id": "legal_review_checklist_builder", "name": "Legal Review Checklist Builder", "subcategory": "legal-ops", "triggers": ["build legal review checklist", "legal review", "legal checklist"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "contract_drafting", "id": "contract_draft_reviewer", "name": "Contract Draft Reviewer", "subcategory": "legal-ops", "triggers": ["review contract draft", "contract drafting", "contract review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "fundraising_prep", "id": "fundraising_readiness_reviewer", "name": "Fundraising Readiness Reviewer", "subcategory": "finance-ops", "triggers": ["review fundraising readiness", "fundraising prep", "fundraising readiness"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "investor_relations", "id": "investor_update_writer", "name": "Investor Update Writer", "subcategory": "finance-communications", "triggers": ["write investor update", "investor relations", "investor communication"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "valuation_methodology", "id": "valuation_methodology_reviewer", "name": "Valuation Methodology Reviewer", "subcategory": "finance-ops", "triggers": ["review valuation methodology", "valuation methodology", "valuation review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "tax_calculation", "id": "tax_calculation_reviewer", "name": "Tax Calculation Reviewer", "subcategory": "finance-compliance", "triggers": ["review tax calculation", "tax calculation", "tax review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "payment_tracking", "id": "payment_tracking_reconciler", "name": "Payment Tracking Reconciler", "subcategory": "finance-ops", "triggers": ["reconcile payment tracking", "payment tracking", "payment status"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "payment_validation", "id": "payment_validation_reviewer", "name": "Payment Validation Reviewer", "subcategory": "finance-ops", "triggers": ["review payment validation", "payment validation", "validate payment"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "invoicing", "id": "invoice_workflow_checker", "name": "Invoice Workflow Checker", "subcategory": "finance-ops", "triggers": ["check invoice workflow", "invoicing", "invoice process"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "pnl", "id": "pnl_statement_reviewer", "name": "PnL Statement Reviewer", "subcategory": "finance-reporting", "triggers": ["review pnl statement", "pnl", "profit and loss statement"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "pl_generation", "id": "profit_loss_draft_builder", "name": "Profit/Loss Draft Builder", "subcategory": "finance-reporting", "triggers": ["build profit loss draft", "pl generation", "profit loss draft"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "pl_projections", "id": "profit_loss_projection_reviewer", "name": "Profit/Loss Projection Reviewer", "subcategory": "finance-reporting", "triggers": ["review profit loss projections", "pl projections", "profit loss forecast"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "daily_profit_alerts", "id": "daily_profit_alert_reviewer", "name": "Daily Profit Alert Reviewer", "subcategory": "finance-reporting", "triggers": ["review daily profit alerts", "daily profit alerts", "profit alert"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
)


def _category(subcategory: str) -> str:
    if subcategory in {"agent-runtime", "skill-system", "reasoning", "memory"}:
        return "Automation & Productivity"
    if subcategory in {"ai-engineering", "testing", "devops", "python", "command-safety", "prompt-security", "security"}:
        return "Development & Technical"
    if subcategory in {"research-security", "research-quality"}:
        return "Research & Analysis"
    if subcategory.startswith("finance"):
        return "Finance & Investment"
    if subcategory == "legal-ops":
        return "Security & Governance"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    approval_note = "Requires human approval before shell execution, memory writeback, context injection, legal/contract use, investor delivery, tax/payment action, or external side effects."
    required_inputs = ["task_goal", "system_context", "constraints"]
    optional_inputs = ["source_materials", "logs", "financial_context", "legal_context", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to runtime, security, research quality, finance, legal, or governance workflows.",
        "Do not invent execution results, legal conclusions, tax advice, payment state, financial records, or source evidence.",
    ]
    if approval:
        when_not.append("Do not perform consequential side effects until a human explicitly approves the prepared review, checklist, or plan.")
    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior systems/governance engineer: ground work in supplied context, separate facts from assumptions, "
        "produce reviewable plans or checks, and never claim execution, legal, tax, payment, or financial actions happened unless verified. "
        f"Primary triggers: {', '.join(spec['triggers'])}. Safety level: {safety}. "
        + (approval_note if approval else "Use read-only or planning-oriented behavior unless routed through an approved execution path.")
    )
    return {
        **old,
        "id": spec["id"],
        "name": spec["name"],
        "category": _category(spec["subcategory"]),
        "subcategory": spec["subcategory"],
        "version": "1.0.0",
        "maturity_level": "production_batch_7",
        "description": f"{spec['name']}: production-ready governance skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reviews, checklists, or quality gates with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {"minimum": "local_reasoning_model_or_cloud_fallback", "preferred": "strong_reasoning_for_security_finance_legal_or_runtime_workflows", "escalate_when": ["low_confidence", "legal_or_finance_risk", "shell_or_memory_side_effect", "external_state_unknown"]},
        "context_requirements": ["Relevant runtime, security, research, finance, or legal context must be supplied or discoverable.", "Approval boundaries and desired output format must be explicit."],
        "memory_usage": {"read": True, "write": spec["id"] in {"agent_memory_health_checker", "long_term_memory_policy_reviewer", "memory_writeback_reviewer"}, "notes": "Use memory for prior governance decisions, runtime policies, finance assumptions, and post-result summaries when useful."},
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_shell_execution", "unapproved_memory_write", "legal_advice_claim", "tax_filing", "payment_execution", "secret_exfiltration"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": approval_note if approval else "Planning, review, or research skill; still surface uncertainty, data gaps, and policy-sensitive recommendations.",
        "system_prompt": system_prompt,
        "developer_prompt": "Respect AscendForge approval gates, auditability, sandboxing, and tenant boundaries. For shell, memory, legal, contract, tax, payment, investor, or financial work, prepare a reviewable artifact first and include blocked actions.",
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with system context {{system_context}} and constraints {{constraints}}.",
        "internal_task_template": {"skill_id": spec["id"], "task_goal": "{{task_goal}}", "system_context": "{{system_context}}", "constraints": "{{constraints}}", "approval_required": approval},
        "examples": [f"Use {spec['name']} to {spec['triggers'][0]}.", f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps."],
        "quality_checklist": ["Uses real supplied or discoverable context.", "States assumptions, missing context, and blocked external actions.", "Separates artifact or findings, rationale, validation, risks, and next steps.", "Does not claim execution, legal, tax, payment, or finance actions unless verified.", "Applies approval gates for shell, memory, legal, contract, investor, tax, payment, and financial side effects."],
        "success_criteria": ["Output is specific enough for review and execution.", "Runtime, security, research, finance, legal, or governance risk is explicit.", "Verification or acceptance checks are included."],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "data_unverified", "policy_boundary"],
        "fallback_strategy": "Return a partial result with assumptions, blocked actions, required approval, and the exact context needed to continue.",
        "audit_events": [f"skill.{spec['id']}.selected", f"skill.{spec['id']}.completed", f"skill.{spec['id']}.blocked"],
        "ui_metadata": {"visible": True, "wired": True, "dashboard_section": "skills", "batch": "batch_7", "status": "production_ready", "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles", "accent": "bronze", "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 241},
        "test_cases": [{"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}}, {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing approval or system context", "expected": {"status": "blocked_or_gap_reported"}}],
        "documentation_status": "documented_batch_7",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-7", "production-skill", "governance"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "security-agent", "finance-agent"}),
        "input_format": {"required_fields": required_inputs, "optional_fields": optional_inputs, "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing execution results, legal conclusions, financial records, or source evidence."},
        "output_format": {"sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"], "format": "structured_markdown", "output_contract": "Every output must show what is checked, drafted, planned, blocked, and what remains unverified."},
        "quality_standards": ["Grounded in real runtime, security, research, finance, legal, or governance context.", "Approval and audit boundaries respected.", "No fake execution, legal advice, tax filing, payment, investor delivery, or financial claims.", f"{spec['name']} passes its production quality checklist."],
        "error_handling": {"retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"], "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "unverified_external_state"], "fallback_strategy": "Return a gap report with the smallest safe next step."},
        "best_practices": ["Inspect supplied context before drafting or recommending action.", "Use existing approval, audit, and skill routing contracts.", "Keep outputs structured, reviewable, and verifiable.", "Never bypass approval for shell, memory, legal, tax, payment, investor, or finance actions."],
        "execution_steps": [f"Classify whether {spec['name']} is the right skill for the goal.", "Collect required context and report gaps.", "Prepare the plan, review, checklist, or quality gate using allowed tools only.", "Apply approval and audit criteria before consequential next action.", "Return artifact, validation, risk notes, approval needs, and next steps."],
        "source": "batch7_production_upgrade",
        "replaces_skill_id": old_id,
    }


def main() -> int:
    data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    skills = data.get("skills", [])
    by_id = {skill.get("id"): idx for idx, skill in enumerate(skills)}
    missing = [spec["replace"] for spec in REPLACEMENTS if spec["replace"] not in by_id and spec["id"] not in by_id]
    if missing:
        raise SystemExit(f"Missing replacement ids: {missing}")
    for spec in REPLACEMENTS:
        idx = by_id[spec["replace"]] if spec["replace"] in by_id else by_id[spec["id"]]
        skills[idx] = build_skill(skills[idx], spec)
    ids = [skill.get("id") for skill in skills]
    duplicates = sorted({skill_id for skill_id in ids if ids.count(skill_id) > 1})
    if duplicates:
        raise SystemExit(f"Duplicate skill ids after upgrade: {duplicates}")
    data.setdefault("_meta", {})
    data["_meta"]["total_skills"] = len(skills)
    data["_meta"]["updated_at"] = date.today().isoformat()
    data["_meta"]["batch7_production_upgrade"] = {"count": len(REPLACEMENTS), "mode": "canonical_replacements_preserve_total", "total_skills_preserved": len(skills)}
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

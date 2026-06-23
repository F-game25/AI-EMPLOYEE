#!/usr/bin/env python3
"""Upgrade the second 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "opportunity_alerts", "id": "opportunity_scanner", "name": "Opportunity Scanner", "subcategory": "money-mode-discovery", "triggers": ["find paid opportunities", "scan work opportunities", "discover money mode tasks"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "deal_matching", "id": "paid_task_evaluator", "name": "Paid Task Evaluator", "subcategory": "money-mode-evaluation", "triggers": ["evaluate paid task", "score client opportunity", "is this task worth doing"], "tools": ["llm_infer", "read_file"], "safety": "medium"},
    {"replace": "creative_briefs", "id": "client_brief_analyzer", "name": "Client Brief Analyzer", "subcategory": "client-work-intake", "triggers": ["analyze client brief", "parse project requirements", "understand client ask"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "pitch_writing", "id": "proposal_writer", "name": "Proposal Writer", "subcategory": "client-work-sales", "triggers": ["write proposal", "client proposal", "pitch paid work"], "tools": ["llm_infer", "read_file"], "safety": "medium", "approval": True},
    {"replace": "quoting", "id": "quote_builder", "name": "Quote Builder", "subcategory": "pricing", "triggers": ["build quote", "estimate price", "quote client work"], "tools": ["llm_infer", "read_file"], "safety": "medium", "approval": True},
    {"replace": "risk_scoring", "id": "scope_risk_assessor", "name": "Scope Risk Assessor", "subcategory": "client-work-risk", "triggers": ["scope risk", "project risk", "scope creep"], "tools": ["llm_infer", "read_file"], "safety": "medium"},
    {"replace": "artifact_tracking", "id": "deliverable_packager", "name": "Deliverable Packager", "subcategory": "delivery", "triggers": ["package deliverable", "prepare client delivery", "bundle output"], "tools": ["read_file", "write_file"], "safety": "high", "approval": True},
    {"replace": "result_validation", "id": "client_delivery_reviewer", "name": "Client Delivery Reviewer", "subcategory": "delivery-quality", "triggers": ["review client delivery", "delivery quality", "final check deliverable"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "revenue_tracking", "id": "earnings_tracker", "name": "Earnings Tracker", "subcategory": "money-mode-reporting", "triggers": ["track earnings", "money mode revenue", "paid task income"], "tools": ["read_file", "write_file"], "safety": "high", "approval": True},
    {"replace": "crm_outcome_monitoring", "id": "money_feedback_analyzer", "name": "Money Feedback Analyzer", "subcategory": "money-mode-feedback", "triggers": ["analyze client feedback", "paid task feedback", "money mode improvement"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "prospect_discovery", "id": "lead_source_finder", "name": "Lead Source Finder", "subcategory": "lead-generation", "triggers": ["find lead sources", "lead source research", "prospect source"], "tools": ["web_search", "read_file"], "safety": "medium"},
    {"replace": "customer_research", "id": "icp_researcher", "name": "ICP Researcher", "subcategory": "lead-generation", "triggers": ["research ideal customer", "icp research", "target customer profile"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "qualification_frameworks", "id": "prospect_qualifier", "name": "Prospect Qualifier", "subcategory": "lead-qualification", "triggers": ["qualify prospect", "score lead fit", "lead qualification"], "tools": ["llm_infer", "read_file"], "safety": "low"},
    {"replace": "outreach_sequences", "id": "outreach_sequence_planner", "name": "Outreach Sequence Planner", "subcategory": "outreach", "triggers": ["plan outreach sequence", "cold outreach plan", "follow up cadence"], "tools": ["llm_infer"], "safety": "medium", "approval": True},
    {"replace": "email_personalization", "id": "email_personalizer", "name": "Email Personalizer", "subcategory": "outreach", "triggers": ["personalize email", "custom outreach email", "tailor cold email"], "tools": ["llm_infer", "read_file"], "safety": "medium", "approval": True},
    {"replace": "crm_management", "id": "crm_update_planner", "name": "CRM Update Planner", "subcategory": "crm", "triggers": ["update crm", "crm workflow", "record lead status"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "content_planning", "id": "content_pipeline_planner", "name": "Content Pipeline Planner", "subcategory": "content-operations", "triggers": ["content pipeline", "plan content calendar", "content workflow"], "tools": ["llm_infer", "read_file"], "safety": "low"},
    {"replace": "content_optimization", "id": "content_quality_reviewer", "name": "Content Quality Reviewer", "subcategory": "content-quality", "triggers": ["review content quality", "content qa", "improve draft"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "post_scheduling", "id": "publish_approval_planner", "name": "Publish Approval Planner", "subcategory": "publishing-approval", "triggers": ["publish approval", "schedule post approval", "prepare publishing"], "tools": ["llm_infer", "read_file"], "safety": "high", "approval": True},
    {"replace": "offer_crafting", "id": "affiliate_offer_evaluator", "name": "Affiliate Offer Evaluator", "subcategory": "affiliate", "triggers": ["evaluate affiliate offer", "affiliate opportunity", "offer quality"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "demand_validation", "id": "ecommerce_product_validator", "name": "Ecommerce Product Validator", "subcategory": "ecommerce-research", "triggers": ["validate product demand", "ecommerce product research", "product opportunity"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "supplier_vetting", "id": "supplier_risk_checker", "name": "Supplier Risk Checker", "subcategory": "supplier-risk", "triggers": ["supplier risk", "vet supplier", "supplier due diligence"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "order_processing", "id": "order_workflow_auditor", "name": "Order Workflow Auditor", "subcategory": "order-operations", "triggers": ["audit order workflow", "order process review", "order operations"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "demand_forecasting", "id": "inventory_signal_analyzer", "name": "Inventory Signal Analyzer", "subcategory": "inventory", "triggers": ["inventory signals", "stock demand signal", "forecast inventory"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "listing_creation", "id": "marketplace_listing_optimizer", "name": "Marketplace Listing Optimizer", "subcategory": "marketplace", "triggers": ["optimize marketplace listing", "listing quality", "marketplace product page"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "ticket_classification", "id": "customer_support_triager", "name": "Customer Support Triager", "subcategory": "customer-support", "triggers": ["triage support ticket", "classify customer issue", "support queue"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "escalation_routing", "id": "support_response_reviewer", "name": "Support Response Reviewer", "subcategory": "customer-support", "triggers": ["review support response", "customer reply quality", "support escalation"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "meeting_summarization", "id": "meeting_summary_writer", "name": "Meeting Summary Writer", "subcategory": "productivity", "triggers": ["write meeting summary", "summarize meeting", "meeting notes"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "meeting_booking", "id": "calendar_schedule_planner", "name": "Calendar Schedule Planner", "subcategory": "productivity", "triggers": ["plan calendar schedule", "schedule meeting", "calendar plan"], "tools": ["llm_infer", "read_file"], "safety": "medium", "approval": True},
    {"replace": "template_management", "id": "workflow_template_builder", "name": "Workflow Template Builder", "subcategory": "workflow-automation", "triggers": ["build workflow template", "template workflow", "repeatable process"], "tools": ["read_file", "write_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "automation_planning", "id": "automation_runbook_writer", "name": "Automation Runbook Writer", "subcategory": "workflow-automation", "triggers": ["write automation runbook", "automation plan", "runbook"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "integration_mapping", "id": "integration_health_checker", "name": "Integration Health Checker", "subcategory": "integration-health", "triggers": ["check integration health", "integration map", "api connection health"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "medium"},
    {"replace": "api_key_verification", "id": "api_key_rotation_planner", "name": "API Key Rotation Planner", "subcategory": "secret-operations", "triggers": ["api key rotation", "rotate credentials", "key lifecycle"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "secure_local_builds", "id": "secrets_exposure_checker", "name": "Secrets Exposure Checker", "subcategory": "security", "triggers": ["check secrets exposure", "secret leak", "credential exposure"], "tools": ["read_file", "grep_patterns"], "safety": "high", "approval": True},
    {"replace": "role_mapping", "id": "tenant_isolation_checker", "name": "Tenant Isolation Checker", "subcategory": "multi-tenant-security", "triggers": ["tenant isolation", "multi tenant boundary", "permission separation"], "tools": ["read_file", "grep_patterns"], "safety": "medium"},
    {"replace": "audit_logging", "id": "audit_log_reviewer", "name": "Audit Log Reviewer", "subcategory": "audit", "triggers": ["review audit logs", "audit trail", "security audit events"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "roi_calculation", "id": "cost_roi_calculator", "name": "Cost ROI Calculator", "subcategory": "finance-ops", "triggers": ["calculate roi", "cost benefit", "money mode roi"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "kpi_tracking", "id": "product_dashboard_metric_mapper", "name": "Product Dashboard Metric Mapper", "subcategory": "dashboard-metrics", "triggers": ["map dashboard metrics", "product kpi dashboard", "metric definitions"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "performance_reviews", "id": "agent_performance_reviewer", "name": "Agent Performance Reviewer", "subcategory": "agent-ops", "triggers": ["review agent performance", "agent scorecard", "agent quality"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "course_outline", "id": "learning_dataset_curator", "name": "Learning Dataset Curator", "subcategory": "learning-data", "triggers": ["curate learning dataset", "training examples", "learning data"], "tools": ["read_file", "write_file", "llm_infer"], "safety": "medium", "approval": True},
)


MONEY_MODE_SUBCATEGORIES = {
    "money-mode-discovery",
    "money-mode-evaluation",
    "client-work-intake",
    "client-work-sales",
    "pricing",
    "client-work-risk",
    "delivery",
    "delivery-quality",
    "money-mode-reporting",
    "money-mode-feedback",
}


def _category(subcategory: str) -> str:
    if subcategory in MONEY_MODE_SUBCATEGORIES:
        return "Money Mode"
    if subcategory in {"lead-generation", "lead-qualification", "outreach", "crm"}:
        return "Lead Generation & Sales"
    if subcategory.startswith("content") or subcategory == "publishing-approval":
        return "Content & Writing"
    if subcategory in {"affiliate", "ecommerce-research", "supplier-risk", "order-operations", "inventory", "marketplace"}:
        return "E-commerce & Product"
    if subcategory in {"customer-support"}:
        return "Customer Support"
    if subcategory in {"secret-operations", "security", "multi-tenant-security", "audit"}:
        return "Security & Governance"
    if subcategory in {"finance-ops"}:
        return "Finance & Investment"
    if subcategory in {"dashboard-metrics", "agent-ops", "learning-data"}:
        return "Automation & Productivity"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    tools = list(spec["tools"])
    side_effect_note = "Requires human approval before publishing, sending, spending, writing files, changing accounts, or touching external systems."

    required_inputs = ["task_goal", "business_context", "constraints"]
    optional_inputs = ["source_materials", "target_audience", "budget", "deadline", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to Money Mode, client delivery, revenue operations, support, or governance.",
        "Do not invent external account state, payments, customer data, or marketplace results.",
    ]
    if approval:
        when_not.append("Do not perform consequential side effects until a human explicitly approves the prepared plan or artifact.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge / Money Mode. "
        "Operate as a senior business-ops engineer: ground work in supplied context, "
        "separate assumptions from facts, produce action-ready artifacts, and never claim external actions happened unless verified. "
        f"Primary triggers: {', '.join(spec['triggers'])}. Safety level: {safety}. "
        + (side_effect_note if approval else "Use read-only or planning-oriented behavior unless explicitly routed through an approved execution path.")
    )
    developer_prompt = (
        "Respect AscendForge approval gates and auditability. "
        "For client, publishing, CRM, payment, credential, or account-adjacent work, prepare a reviewable plan or draft first. "
        "Include validation checks, blocked actions, and the smallest safe next step."
    )

    return {
        **old,
        "id": spec["id"],
        "name": spec["name"],
        "category": _category(spec["subcategory"]),
        "subcategory": spec["subcategory"],
        "version": "1.0.0",
        "maturity_level": "production_batch_2",
        "description": f"{spec['name']}: production-ready Money Mode and operations skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, drafts, reviews, or checks with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_business_risk_security_or_multi_step_workflows",
            "escalate_when": ["low_confidence", "money_or_client_risk", "external_side_effect", "credential_or_account_boundary"],
        },
        "context_requirements": [
            "Relevant client, opportunity, product, support, audit, or workflow context must be supplied or discoverable.",
            "Approval boundaries and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"earnings_tracker", "money_feedback_analyzer", "agent_performance_reviewer", "learning_dataset_curator"},
            "notes": "Use memory for prior client decisions, pricing patterns, reusable workflow lessons, and post-result summaries when useful.",
        },
        "tools_allowed": tools,
        "tools_forbidden": ["unapproved_external_delivery", "unapproved_account_change", "payment_execution", "wallet_access", "secret_exfiltration", "mass_messaging"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": side_effect_note if approval else "Planning or review skill; still surface uncertainty, data gaps, and policy-sensitive recommendations.",
        "system_prompt": system_prompt,
        "developer_prompt": developer_prompt,
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with business context {{business_context}} and constraints {{constraints}}.",
        "internal_task_template": {
            "skill_id": spec["id"],
            "task_goal": "{{task_goal}}",
            "business_context": "{{business_context}}",
            "constraints": "{{constraints}}",
            "approval_required": approval,
        },
        "examples": [
            f"Use {spec['name']} to {spec['triggers'][0]} for a Money Mode workflow.",
            f"Run {spec['name']} and return output, assumptions, risks, approval needs, and validation steps.",
        ],
        "quality_checklist": [
            "Uses real supplied or discoverable business/system context.",
            "States assumptions, missing context, and blocked external actions.",
            "Separates artifact, rationale, validation, risks, and next steps.",
            "Does not claim publishing, delivery, account updates, payment, or file writes unless actually executed through approval.",
            "Applies approval gates for money, client, publishing, credential, account, and write-side effects.",
        ],
        "success_criteria": [
            "Output is specific enough for a human or agent to review and execute.",
            "Money, client, account, or security risk is explicit.",
            "Verification or acceptance checks are included.",
        ],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "data_unverified", "policy_boundary"],
        "fallback_strategy": "Return a partial result with assumptions, blocked actions, required approval, and the exact context needed to continue.",
        "audit_events": [
            f"skill.{spec['id']}.selected",
            f"skill.{spec['id']}.completed",
            f"skill.{spec['id']}.blocked",
        ],
        "ui_metadata": {
            "visible": True,
            "wired": True,
            "dashboard_section": "skills",
            "batch": "batch_2",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "gold",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 41,
        },
        "test_cases": [
            {
                "name": f"selects_{spec['id']}",
                "input": spec["triggers"][0],
                "expected": {"selected_skill_id": spec["id"], "status": "selected"},
            },
            {
                "name": f"approval_or_gap_behavior_{spec['id']}",
                "input": "missing approval or business context",
                "expected": {"status": "blocked_or_gap_reported"},
            },
        ],
        "documentation_status": "documented_batch_2",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-2", "production-skill", "money-mode"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "money-mode-agent", "business-ops-agent"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing business context rather than inventing customer, payment, or account state.",
        },
        "output_format": {
            "sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what is drafted, checked, planned, blocked, and what remains unverified.",
        },
        "quality_standards": [
            "Grounded in real business or system context.",
            "Approval and audit boundaries respected.",
            "No fake integrations, customer actions, payments, or external delivery claims.",
            f"{spec['name']} passes its production quality checklist.",
        ],
        "error_handling": {
            "retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"],
            "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "unverified_external_state"],
            "fallback_strategy": "Return a gap report with the smallest safe next step.",
        },
        "best_practices": [
            "Inspect supplied context before drafting or recommending action.",
            "Use existing approval, audit, and skill routing contracts.",
            "Keep outputs structured, reviewable, and verifiable.",
            "Never bypass approval for money, client, account, credential, or publishing actions.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required business and system context and report gaps.",
            "Prepare the plan, draft, review, or check using allowed tools only.",
            "Apply approval and audit criteria before any consequential next action.",
            "Return artifact, validation, risk notes, approval needs, and next steps.",
        ],
        "source": "batch2_production_upgrade",
        "replaces_skill_id": old_id,
    }


def main() -> int:
    data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    skills = data.get("skills", [])
    by_id = {skill.get("id"): idx for idx, skill in enumerate(skills)}
    missing = [
        spec["replace"]
        for spec in REPLACEMENTS
        if spec["replace"] not in by_id and spec["id"] not in by_id
    ]
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
    data["_meta"]["batch2_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

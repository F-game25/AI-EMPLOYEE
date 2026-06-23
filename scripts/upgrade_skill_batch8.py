#!/usr/bin/env python3
"""Upgrade the eighth 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "a_b_testing_emails", "id": "email_ab_test_analyzer", "name": "Email A/B Test Analyzer", "subcategory": "email-growth", "triggers": ["analyze email ab test", "a b testing emails", "email experiment results"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "ab_testing_framework", "id": "growth_ab_test_plan_reviewer", "name": "Growth A/B Test Plan Reviewer", "subcategory": "growth-experiments", "triggers": ["review growth ab test plan", "ab testing framework", "experiment design review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "accessibility_audit", "id": "accessibility_audit_checker", "name": "Accessibility Audit Checker", "subcategory": "ui-quality", "triggers": ["check accessibility audit", "accessibility audit", "wcag review"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "alert_formatting", "id": "trading_alert_format_reviewer", "name": "Trading Alert Format Reviewer", "subcategory": "trading-comms", "triggers": ["review trading alert format", "alert formatting", "market alert copy"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "audit_trail", "id": "customer_audit_trail_reviewer", "name": "Customer Audit Trail Reviewer", "subcategory": "customer-ops", "triggers": ["review customer audit trail", "audit trail", "support audit history"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "brand_positioning", "id": "brand_positioning_reviewer", "name": "Brand Positioning Reviewer", "subcategory": "brand-strategy", "triggers": ["review brand positioning", "brand positioning", "positioning statement"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "budget_allocation", "id": "marketing_budget_allocation_reviewer", "name": "Marketing Budget Allocation Reviewer", "subcategory": "marketing-ops", "triggers": ["review marketing budget allocation", "budget allocation", "ad budget split"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "campaign_ideation", "id": "campaign_idea_brief_builder", "name": "Campaign Idea Brief Builder", "subcategory": "campaign-planning", "triggers": ["build campaign idea brief", "campaign ideation", "marketing campaign ideas"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "campaign_scheduling", "id": "campaign_schedule_planner", "name": "Campaign Schedule Planner", "subcategory": "campaign-planning", "triggers": ["plan campaign schedule", "campaign scheduling", "launch calendar"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "candidate_outreach", "id": "candidate_outreach_message_reviewer", "name": "Candidate Outreach Message Reviewer", "subcategory": "people-ops", "triggers": ["review candidate outreach message", "candidate outreach", "recruiting message"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "color_palette_design", "id": "color_palette_system_reviewer", "name": "Color Palette System Reviewer", "subcategory": "brand-design", "triggers": ["review color palette system", "color palette design", "brand color palette"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "comment_automation", "id": "comment_automation_safety_reviewer", "name": "Comment Automation Safety Reviewer", "subcategory": "social-automation", "triggers": ["review comment automation safety", "comment automation", "automated social comments"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "compensation_benchmarking", "id": "compensation_benchmark_brief_builder", "name": "Compensation Benchmark Brief Builder", "subcategory": "people-ops", "triggers": ["build compensation benchmark brief", "compensation benchmarking", "pay benchmark"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "competitive_brand_analysis", "id": "competitive_brand_analysis_reviewer", "name": "Competitive Brand Analysis Reviewer", "subcategory": "brand-strategy", "triggers": ["review competitive brand analysis", "competitive brand analysis", "brand competitors"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "component_specification", "id": "component_spec_writer", "name": "Component Spec Writer", "subcategory": "design-system", "triggers": ["write component spec", "component specification", "ui component requirements"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "content_curation", "id": "content_curation_planner", "name": "Content Curation Planner", "subcategory": "content-ops", "triggers": ["plan content curation", "content curation", "curated content plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "content_generation", "id": "social_content_generation_reviewer", "name": "Social Content Generation Reviewer", "subcategory": "social-content", "triggers": ["review social content generation", "content generation", "generated social post"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "conversion_optimization", "id": "conversion_optimization_planner", "name": "Conversion Optimization Planner", "subcategory": "growth-experiments", "triggers": ["plan conversion optimization", "conversion optimization", "cro plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "conversion_tracking", "id": "conversion_tracking_checker", "name": "Conversion Tracking Checker", "subcategory": "analytics", "triggers": ["check conversion tracking", "conversion tracking", "tracking pixel audit"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "medium"},
    {"replace": "cost_tracking", "id": "operating_cost_tracking_reviewer", "name": "Operating Cost Tracking Reviewer", "subcategory": "ops-finance", "triggers": ["review operating cost tracking", "cost tracking", "expense tracking"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "crypto_community_building", "id": "crypto_community_growth_planner", "name": "Crypto Community Growth Planner", "subcategory": "web3-growth", "triggers": ["plan crypto community growth", "crypto community building", "web3 community plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "dark_mode_design", "id": "dark_mode_accessibility_reviewer", "name": "Dark Mode Accessibility Reviewer", "subcategory": "ui-quality", "triggers": ["review dark mode accessibility", "dark mode design", "dark theme contrast"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "data_analysis", "id": "data_analysis_plan_reviewer", "name": "Data Analysis Plan Reviewer", "subcategory": "analytics", "triggers": ["review data analysis plan", "data analysis", "analysis methodology"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "deliverability_optimization", "id": "email_deliverability_optimization_checker", "name": "Email Deliverability Optimization Checker", "subcategory": "email-growth", "triggers": ["check email deliverability optimization", "deliverability optimization", "email inbox placement"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "developer_handoff", "id": "developer_handoff_package_reviewer", "name": "Developer Handoff Package Reviewer", "subcategory": "design-system", "triggers": ["review developer handoff package", "developer handoff", "handoff checklist"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "dns_verification", "id": "dns_verification_checklist_builder", "name": "DNS Verification Checklist Builder", "subcategory": "email-infra", "triggers": ["build dns verification checklist", "dns verification", "spf dkim dmarc check"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "document_generation", "id": "document_generation_reviewer", "name": "Document Generation Reviewer", "subcategory": "document-ops", "triggers": ["review document generation", "document generation", "generated document quality"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "drip_sequences", "id": "drip_sequence_planner", "name": "Drip Sequence Planner", "subcategory": "email-growth", "triggers": ["plan drip sequence", "drip sequences", "email drip campaign"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "earnings_quality", "id": "earnings_quality_reviewer", "name": "Earnings Quality Reviewer", "subcategory": "finance-research", "triggers": ["review earnings quality", "earnings quality", "quality of earnings"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "email_composition", "id": "email_composition_reviewer", "name": "Email Composition Reviewer", "subcategory": "email-growth", "triggers": ["review email composition", "email composition", "email draft review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "email_sequence", "id": "email_sequence_planner", "name": "Email Sequence Planner", "subcategory": "email-growth", "triggers": ["plan email sequence", "email sequence", "multi email campaign"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "engagement_tracking", "id": "engagement_tracking_reporter", "name": "Engagement Tracking Reporter", "subcategory": "analytics", "triggers": ["report engagement tracking", "engagement tracking", "engagement metrics"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "follow_up_automation", "id": "follow_up_automation_planner", "name": "Follow-Up Automation Planner", "subcategory": "sales-ops", "triggers": ["plan follow up automation", "follow up automation", "automated follow up workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "follow_up_generation", "id": "follow_up_message_writer", "name": "Follow-Up Message Writer", "subcategory": "sales-ops", "triggers": ["write follow up message", "follow up generation", "follow up email"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "follow_up_sequencing", "id": "follow_up_sequence_reviewer", "name": "Follow-Up Sequence Reviewer", "subcategory": "sales-ops", "triggers": ["review follow up sequence", "follow up sequencing", "sales follow up cadence"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "image_prompt_creation", "id": "image_prompt_brief_builder", "name": "Image Prompt Brief Builder", "subcategory": "creative-ops", "triggers": ["build image prompt brief", "image prompt creation", "visual prompt brief"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "image_prompts", "id": "image_prompt_safety_reviewer", "name": "Image Prompt Safety Reviewer", "subcategory": "creative-ops", "triggers": ["review image prompt safety", "image prompts", "visual prompt safety"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "improvement_proposals", "id": "improvement_proposal_prioritizer", "name": "Improvement Proposal Prioritizer", "subcategory": "strategy-ops", "triggers": ["prioritize improvement proposals", "improvement proposals", "proposal prioritization"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "interview_scheduling", "id": "interview_schedule_planner", "name": "Interview Schedule Planner", "subcategory": "people-ops", "triggers": ["plan interview schedule", "interview scheduling", "candidate interview calendar"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "keyword_search", "id": "keyword_search_plan_builder", "name": "Keyword Search Plan Builder", "subcategory": "search-research", "triggers": ["build keyword search plan", "keyword search", "search keyword plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
)


def _category(subcategory: str) -> str:
    if subcategory in {"email-growth", "campaign-planning", "social-automation", "social-content", "marketing-ops", "brand-strategy", "growth-experiments", "web3-growth"}:
        return "Growth & Marketing"
    if subcategory in {"brand-design", "design-system", "ui-quality", "creative-ops"}:
        return "Branding & Identity"
    if subcategory in {"analytics", "ops-finance", "finance-research", "trading-comms"}:
        return "Finance & Investment"
    if subcategory in {"sales-ops", "email-infra"}:
        return "Lead Generation & Sales"
    if subcategory in {"people-ops", "customer-ops", "document-ops", "strategy-ops"}:
        return "Automation & Productivity"
    if subcategory == "search-research":
        return "Research & Analysis"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = sorted({old_id, old_id.replace("_", "-"), *old.get("aliases", [])} - {spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    required_inputs = ["task_goal", "audience_or_system_context", "constraints"]
    optional_inputs = ["source_materials", "brand_guidelines", "analytics_snapshot", "approval_context", "previous_results"]
    approval_note = "Requires human approval before external outreach, trading/investment messaging, automated social comments, candidate contact, or customer-facing delivery."
    when_not = [
        "Do not use when the request is unrelated to growth, content, brand, sales, analytics, people, or customer operations.",
        "Do not invent analytics, audience data, brand rules, market evidence, DNS state, or delivery outcomes.",
    ]
    if approval:
        when_not.append("Do not send, publish, automate, or contact anyone until a human approves the prepared artifact.")
    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior go-to-market, brand, and operations reviewer: ground work in supplied context, mark missing evidence, "
        "produce reviewable artifacts, and never claim publication, delivery, contact, or analytics verification unless proven. "
        f"Primary triggers: {', '.join(spec['triggers'])}. Safety level: {safety}. "
        + (approval_note if approval else "Use planning and review behavior by default, with no external side effects.")
    )
    return {
        **old,
        "id": spec["id"],
        "name": spec["name"],
        "category": _category(spec["subcategory"]),
        "subcategory": spec["subcategory"],
        "version": "1.0.0",
        "maturity_level": "production_batch_8",
        "description": f"{spec['name']}: production-ready skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reviews, briefs, checklists, or quality gates.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {"minimum": "local_reasoning_model_or_cloud_fallback", "preferred": "strong_reasoning_for_growth_brand_sales_and_analytics_workflows", "escalate_when": ["low_confidence", "external_delivery_requested", "regulated_or_financial_claims", "audience_or_brand_context_missing"]},
        "context_requirements": ["Relevant audience, brand, campaign, analytics, sales, people, or customer context must be supplied or discoverable.", "Approval boundaries and delivery channel must be explicit for customer-facing work."],
        "memory_usage": {"read": True, "write": False, "notes": "Use memory for prior brand rules, campaign decisions, and accepted operating assumptions; do not write unless routed through an approved memory skill."},
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_publish", "unapproved_outreach", "unapproved_social_automation", "unapproved_trading_signal_delivery", "secret_exfiltration", "fabricated_metrics"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe",
        "approval_policy": "human_approval_required_for_external_delivery" if approval else "read_or_plan_without_external_side_effects",
        "risk_notes": approval_note if approval else "Planning or review skill; still surface uncertainty, missing evidence, and customer-facing risk.",
        "system_prompt": system_prompt,
        "developer_prompt": "Respect AscendForge approval gates, auditability, tenant boundaries, and Money Mode delivery rules. Prepare reviewable artifacts first; never publish, contact, automate comments, or send trading/customer-facing messages without approval.",
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with context {{audience_or_system_context}} and constraints {{constraints}}.",
        "internal_task_template": {"skill_id": spec["id"], "task_goal": "{{task_goal}}", "audience_or_system_context": "{{audience_or_system_context}}", "constraints": "{{constraints}}", "approval_required": approval},
        "examples": [f"Use {spec['name']} to {spec['triggers'][0]}.", f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps."],
        "quality_checklist": ["Uses supplied brand, audience, campaign, analytics, or customer context.", "States assumptions and missing evidence.", "Separates artifact, rationale, validation, risks, approval needs, and next steps.", "Does not claim publication, outreach, comment automation, DNS verification, or analytics results without proof.", "Applies approval gates for customer-facing, candidate-facing, social automation, email, and trading communication outputs."],
        "success_criteria": ["Output is specific enough for review or execution by an approved operator.", "Messaging, brand, analytics, or operational risk is explicit.", "Verification or acceptance checks are included."],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "unverified_metrics", "policy_boundary"],
        "fallback_strategy": "Return a partial artifact with assumptions, blocked delivery actions, required approval, and exact context needed to continue.",
        "audit_events": [f"skill.{spec['id']}.selected", f"skill.{spec['id']}.completed", f"skill.{spec['id']}.blocked"],
        "ui_metadata": {"visible": True, "wired": True, "dashboard_section": "skills", "batch": "batch_8", "status": "production_ready", "icon": "send" if approval else "chart", "accent": "gold", "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 281},
        "test_cases": [{"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}}, {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing audience or approval context", "expected": {"status": "blocked_or_gap_reported"}}],
        "documentation_status": "documented_batch_8",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-8", "production-skill", "go-to-market"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "money-agent", "growth-agent"}),
        "input_format": {"required_fields": required_inputs, "optional_fields": optional_inputs, "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing metrics, delivery results, or brand evidence."},
        "output_format": {"sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"], "format": "structured_markdown", "output_contract": "Every output must show what is drafted, reviewed, planned, blocked, and unverified."},
        "quality_standards": ["Grounded in real brand, audience, campaign, analytics, customer, or sales context.", "Approval and audit boundaries respected.", "No fake delivery, publication, analytics, outreach, or DNS verification claims.", f"{spec['name']} passes its production quality checklist."],
        "error_handling": {"retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"], "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "unverified_external_state"], "fallback_strategy": "Return a gap report with the smallest safe next step."},
        "best_practices": ["Inspect supplied context before drafting or recommending action.", "Use existing approval, audit, and skill routing contracts.", "Keep outputs structured, reviewable, and verifiable.", "Never bypass approval for customer-facing, candidate-facing, social automation, email, or trading communication actions."],
        "execution_steps": [f"Classify whether {spec['name']} is the right skill for the goal.", "Collect required context and report gaps.", "Prepare the plan, review, brief, checklist, or quality gate using allowed tools only.", "Apply approval and audit criteria before external delivery.", "Return artifact, validation, risk notes, approval needs, and next steps."],
        "source": "batch8_production_upgrade",
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
    data["_meta"]["batch8_production_upgrade"] = {"count": len(REPLACEMENTS), "mode": "canonical_replacements_preserve_total", "total_skills_preserved": len(skills)}
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

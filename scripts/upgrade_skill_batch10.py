#!/usr/bin/env python3
"""Upgrade the final 11 production skills in-place without changing count.

Batch 10 completes the agent_capability_backfill -> production upgrade campaign:
after this batch there are no weak generated skills left in the library.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "trend_analysis", "id": "trend_analysis_brief_builder", "name": "Trend Analysis Brief Builder", "subcategory": "search-research", "triggers": ["build trend analysis brief", "trend analysis", "emerging trend report"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "typography_system", "id": "typography_system_reviewer", "name": "Typography System Reviewer", "subcategory": "brand-design", "triggers": ["review typography system", "typography system", "type scale review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "user_flow_design", "id": "user_flow_design_reviewer", "name": "User Flow Design Reviewer", "subcategory": "ux-design", "triggers": ["review user flow design", "user flow design", "ux flow review"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "ux_writing", "id": "ux_writing_reviewer", "name": "UX Writing Reviewer", "subcategory": "ux-design", "triggers": ["review ux writing", "ux writing", "microcopy review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "viral_content_creation", "id": "viral_content_reviewer", "name": "Viral Content Reviewer", "subcategory": "social-content", "triggers": ["review viral content", "viral content creation", "viral post review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "viral_marketing", "id": "viral_marketing_plan_reviewer", "name": "Viral Marketing Plan Reviewer", "subcategory": "growth-experiments", "triggers": ["review viral marketing plan", "viral marketing", "viral campaign plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "viral_mechanics", "id": "viral_loop_mechanics_reviewer", "name": "Viral Loop Mechanics Reviewer", "subcategory": "growth-experiments", "triggers": ["review viral loop mechanics", "viral mechanics", "referral loop design"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "visual_identity_brief", "id": "visual_identity_brief_builder", "name": "Visual Identity Brief Builder", "subcategory": "brand-design", "triggers": ["build visual identity brief", "visual identity brief", "brand identity brief"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "warmup_planning", "id": "email_warmup_plan_builder", "name": "Email Warmup Plan Builder", "subcategory": "email-infra", "triggers": ["build email warmup plan", "warmup planning", "inbox warmup schedule"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "website_audit", "id": "website_audit_checker", "name": "Website Audit Checker", "subcategory": "seo", "triggers": ["check website audit", "website audit", "site quality audit"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "whatsapp_notifications", "id": "whatsapp_notification_reviewer", "name": "WhatsApp Notification Reviewer", "subcategory": "comms-automation", "triggers": ["review whatsapp notification", "whatsapp notifications", "whatsapp message policy"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
)


def _category(subcategory: str) -> str:
    if subcategory in {"growth-experiments"}:
        return "Growth & Marketing"
    if subcategory in {"search-research"}:
        return "Research & Analysis"
    if subcategory in {"seo"}:
        return "Marketing & SEO"
    if subcategory in {"email-infra"}:
        return "Lead Generation & Sales"
    if subcategory in {"social-content"}:
        return "Social Media"
    if subcategory in {"comms-automation"}:
        return "Communication Channels"
    if subcategory in {"brand-design", "ux-design"}:
        return "Branding & Identity"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = sorted({old_id, old_id.replace("_", "-"), *old.get("aliases", [])} - {spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    required_inputs = ["task_goal", "audience_or_system_context", "constraints"]
    optional_inputs = ["source_materials", "brand_guidelines", "analytics_snapshot", "approval_context", "previous_results"]
    approval_note = "Requires human approval before content publication, notification/messaging delivery, or any customer-facing delivery."
    when_not = [
        "Do not use when the request is unrelated to growth, brand, design, UX, content, research, or messaging review.",
        "Do not invent analytics, audience data, brand rules, market evidence, or delivery outcomes.",
    ]
    if approval:
        when_not.append("Do not publish, send, or contact anyone until a human approves the prepared artifact.")
    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior growth, brand, design, UX, and messaging reviewer: ground work in supplied context, mark missing "
        "evidence, produce reviewable artifacts, and never claim publication, delivery, or analytics verification unless proven. "
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
        "maturity_level": "production_batch_10",
        "description": f"{spec['name']}: production-ready skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reviews, briefs, checklists, or quality gates.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {"minimum": "local_reasoning_model_or_cloud_fallback", "preferred": "strong_reasoning_for_growth_brand_design_ux_and_messaging_workflows", "escalate_when": ["low_confidence", "external_delivery_requested", "content_publication_requested", "audience_or_brand_context_missing"]},
        "context_requirements": ["Relevant audience, brand, design, UX, campaign, or messaging context must be supplied or discoverable.", "Approval boundaries and delivery channel must be explicit for customer-facing, publication, or messaging work."],
        "memory_usage": {"read": True, "write": False, "notes": "Use memory for prior brand rules, design decisions, and accepted operating assumptions; do not write unless routed through an approved memory skill."},
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_publish", "unapproved_outreach", "unapproved_notification_send", "unapproved_social_automation", "secret_exfiltration", "fabricated_metrics"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe",
        "approval_policy": "human_approval_required_for_external_delivery" if approval else "read_or_plan_without_external_side_effects",
        "risk_notes": approval_note if approval else "Planning or review skill; still surface uncertainty, missing evidence, and customer-facing risk.",
        "system_prompt": system_prompt,
        "developer_prompt": "Respect AscendForge approval gates, auditability, tenant boundaries, and Money Mode delivery rules. Prepare reviewable artifacts first; never publish, contact, or send notifications without approval.",
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with context {{audience_or_system_context}} and constraints {{constraints}}.",
        "internal_task_template": {"skill_id": spec["id"], "task_goal": "{{task_goal}}", "audience_or_system_context": "{{audience_or_system_context}}", "constraints": "{{constraints}}", "approval_required": approval},
        "examples": [f"Use {spec['name']} to {spec['triggers'][0]}.", f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps."],
        "quality_checklist": ["Uses supplied brand, audience, design, UX, campaign, or messaging context.", "States assumptions and missing evidence.", "Separates artifact, rationale, validation, risks, approval needs, and next steps.", "Does not claim publication, outreach, notification delivery, or analytics results without proof.", "Applies approval gates for customer-facing, content publication, and messaging outputs."],
        "success_criteria": ["Output is specific enough for review or execution by an approved operator.", "Messaging, brand, design, or operational risk is explicit.", "Verification or acceptance checks are included."],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "unverified_metrics", "policy_boundary"],
        "fallback_strategy": "Return a partial artifact with assumptions, blocked delivery actions, required approval, and exact context needed to continue.",
        "audit_events": [f"skill.{spec['id']}.selected", f"skill.{spec['id']}.completed", f"skill.{spec['id']}.blocked"],
        "ui_metadata": {"visible": True, "wired": True, "dashboard_section": "skills", "batch": "batch_10", "status": "production_ready", "icon": "send" if approval else "chart", "accent": "gold", "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 361},
        "test_cases": [{"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}}, {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing audience or approval context", "expected": {"status": "blocked_or_gap_reported"}}],
        "documentation_status": "documented_batch_10",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-10", "production-skill", "go-to-market"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "money-agent", "growth-agent"}),
        "input_format": {"required_fields": required_inputs, "optional_fields": optional_inputs, "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing metrics, delivery results, or brand evidence."},
        "output_format": {"sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"], "format": "structured_markdown", "output_contract": "Every output must show what is drafted, reviewed, planned, blocked, and unverified."},
        "quality_standards": ["Grounded in real brand, audience, design, UX, campaign, or messaging context.", "Approval and audit boundaries respected.", "No fake delivery, publication, analytics, or outreach claims.", f"{spec['name']} passes its production quality checklist."],
        "error_handling": {"retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"], "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "unverified_external_state"], "fallback_strategy": "Return a gap report with the smallest safe next step."},
        "best_practices": ["Inspect supplied context before drafting or recommending action.", "Use existing approval, audit, and skill routing contracts.", "Keep outputs structured, reviewable, and verifiable.", "Never bypass approval for customer-facing, content publication, or messaging actions."],
        "execution_steps": [f"Classify whether {spec['name']} is the right skill for the goal.", "Collect required context and report gaps.", "Prepare the plan, review, brief, checklist, or quality gate using allowed tools only.", "Apply approval and audit criteria before external delivery.", "Return artifact, validation, risk notes, approval needs, and next steps."],
        "source": "batch10_production_upgrade",
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
    data["_meta"]["batch10_production_upgrade"] = {"count": len(REPLACEMENTS), "mode": "canonical_replacements_preserve_total", "total_skills_preserved": len(skills)}
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

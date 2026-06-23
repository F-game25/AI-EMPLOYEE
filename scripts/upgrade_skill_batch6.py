#!/usr/bin/env python3
"""Upgrade the sixth 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "action_item_extraction", "id": "action_item_tracker", "name": "Action Item Tracker", "subcategory": "productivity", "triggers": ["track action items", "extract action items", "follow up actions"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "note_creation", "id": "meeting_note_structurer", "name": "Meeting Note Structurer", "subcategory": "productivity", "triggers": ["structure meeting notes", "note creation", "meeting notes"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "transcript_analysis", "id": "transcript_insight_extractor", "name": "Transcript Insight Extractor", "subcategory": "productivity", "triggers": ["extract transcript insights", "transcript analysis", "meeting transcript"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "scheduling", "id": "schedule_conflict_planner", "name": "Schedule Conflict Planner", "subcategory": "productivity", "triggers": ["plan schedule conflicts", "scheduling", "calendar conflict"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "gantt_planning", "id": "gantt_timeline_reviewer", "name": "Gantt Timeline Reviewer", "subcategory": "project-planning", "triggers": ["review gantt timeline", "gantt planning", "timeline review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "work_breakdown_structure", "id": "work_breakdown_builder", "name": "Work Breakdown Builder", "subcategory": "project-planning", "triggers": ["build work breakdown", "work breakdown structure", "wbs"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "progress_tracking", "id": "project_progress_reporter", "name": "Project Progress Reporter", "subcategory": "project-reporting", "triggers": ["report project progress", "progress tracking", "project status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "retrospective_facilitation", "id": "retrospective_action_planner", "name": "Retrospective Action Planner", "subcategory": "project-improvement", "triggers": ["plan retrospective actions", "retrospective facilitation", "retro action items"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "team_coordination", "id": "team_coordination_brief_builder", "name": "Team Coordination Brief Builder", "subcategory": "team-ops", "triggers": ["build team coordination brief", "team coordination", "team handoff"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "task_assignment", "id": "task_assignment_reviewer", "name": "Task Assignment Reviewer", "subcategory": "team-ops", "triggers": ["review task assignment", "task assignment", "assignment ownership"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "task_scheduling", "id": "task_schedule_optimizer", "name": "Task Schedule Optimizer", "subcategory": "team-ops", "triggers": ["optimize task schedule", "task scheduling", "schedule tasks"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "goal_management", "id": "goal_health_reviewer", "name": "Goal Health Reviewer", "subcategory": "goal-ops", "triggers": ["review goal health", "goal management", "goal status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "goal_decomposition", "id": "goal_decomposition_reviewer", "name": "Goal Decomposition Reviewer", "subcategory": "goal-ops", "triggers": ["review goal decomposition", "goal decomposition", "break down goal"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "workflow_design", "id": "workflow_design_reviewer", "name": "Workflow Design Reviewer", "subcategory": "workflow-ops", "triggers": ["review workflow design", "workflow design", "process design"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "workflow_generation", "id": "workflow_generation_planner", "name": "Workflow Generation Planner", "subcategory": "workflow-ops", "triggers": ["plan workflow generation", "workflow generation", "generate workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "workflow_management", "id": "workflow_management_auditor", "name": "Workflow Management Auditor", "subcategory": "workflow-ops", "triggers": ["audit workflow management", "workflow management", "workflow health"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "company_management", "id": "company_operating_system_mapper", "name": "Company Operating System Mapper", "subcategory": "company-ops", "triggers": ["map company operating system", "company management", "operating model"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "mission_tracking", "id": "mission_progress_tracker", "name": "Mission Progress Tracker", "subcategory": "company-ops", "triggers": ["track mission progress", "mission tracking", "mission status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "hierarchy_modeling", "id": "org_hierarchy_mapper", "name": "Org Hierarchy Mapper", "subcategory": "company-ops", "triggers": ["map org hierarchy", "hierarchy modeling", "organization structure"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "reporting_lines", "id": "reporting_line_reviewer", "name": "Reporting Line Reviewer", "subcategory": "company-ops", "triggers": ["review reporting lines", "reporting lines", "ownership lines"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "workload_tracking", "id": "workload_balance_checker", "name": "Workload Balance Checker", "subcategory": "company-ops", "triggers": ["check workload balance", "workload tracking", "team capacity"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "amazon_research", "id": "amazon_product_researcher", "name": "Amazon Product Researcher", "subcategory": "commerce-research", "triggers": ["research amazon product", "amazon research", "amazon marketplace"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "marketplace_analysis", "id": "marketplace_competition_analyzer", "name": "Marketplace Competition Analyzer", "subcategory": "commerce-research", "triggers": ["analyze marketplace competition", "marketplace analysis", "marketplace competitor"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "listing_automation", "id": "listing_automation_planner", "name": "Listing Automation Planner", "subcategory": "commerce-ops", "triggers": ["plan listing automation", "listing automation", "marketplace listing workflow"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "supplier_api_integration", "id": "supplier_api_contract_reviewer", "name": "Supplier API Contract Reviewer", "subcategory": "supplier-ops", "triggers": ["review supplier api contract", "supplier api integration", "supplier contract"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "supplier_api_sync", "id": "supplier_api_sync_checker", "name": "Supplier API Sync Checker", "subcategory": "supplier-ops", "triggers": ["check supplier api sync", "supplier api sync", "supplier sync health"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "low_stock_alerts", "id": "low_stock_alert_planner", "name": "Low Stock Alert Planner", "subcategory": "inventory-ops", "triggers": ["plan low stock alerts", "low stock alerts", "stock alert rule"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "auto_reorder", "id": "auto_reorder_policy_reviewer", "name": "Auto-Reorder Policy Reviewer", "subcategory": "inventory-ops", "triggers": ["review auto reorder policy", "auto reorder", "reorder policy"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "order_routing", "id": "order_routing_rule_auditor", "name": "Order Routing Rule Auditor", "subcategory": "order-ops", "triggers": ["audit order routing rules", "order routing", "routing rule"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "order_tracking", "id": "order_tracking_status_reporter", "name": "Order Tracking Status Reporter", "subcategory": "order-ops", "triggers": ["report order tracking status", "order tracking", "order status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "tracking_updates", "id": "shipment_tracking_update_writer", "name": "Shipment Tracking Update Writer", "subcategory": "order-communications", "triggers": ["write shipment tracking update", "tracking updates", "shipment status"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "price_comparison", "id": "price_comparison_researcher", "name": "Price Comparison Researcher", "subcategory": "commerce-pricing", "triggers": ["research price comparison", "price comparison", "compare prices"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "price_monitoring", "id": "price_monitoring_rule_planner", "name": "Price Monitoring Rule Planner", "subcategory": "commerce-pricing", "triggers": ["plan price monitoring rules", "price monitoring", "pricing alert"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "stock_monitoring", "id": "stock_monitoring_reporter", "name": "Stock Monitoring Reporter", "subcategory": "inventory-ops", "triggers": ["report stock monitoring", "stock monitoring", "inventory status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "trend_detection", "id": "ecommerce_trend_detector", "name": "Ecommerce Trend Detector", "subcategory": "commerce-research", "triggers": ["detect ecommerce trends", "trend detection", "product trend"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "trend_spotting", "id": "trend_spotting_brief_builder", "name": "Trend Spotting Brief Builder", "subcategory": "commerce-research", "triggers": ["build trend spotting brief", "trend spotting", "trend brief"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "top_product_ranking", "id": "top_product_ranking_reviewer", "name": "Top Product Ranking Reviewer", "subcategory": "commerce-research", "triggers": ["review top product ranking", "top product ranking", "product ranking"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "product_design", "id": "product_design_brief_reviewer", "name": "Product Design Brief Reviewer", "subcategory": "product-ops", "triggers": ["review product design brief", "product design", "product brief"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "customer_segmentation", "id": "customer_segment_analyzer", "name": "Customer Segment Analyzer", "subcategory": "growth-research", "triggers": ["analyze customer segments", "customer segmentation", "segment analysis"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "niche_targeting", "id": "niche_targeting_reviewer", "name": "Niche Targeting Reviewer", "subcategory": "growth-research", "triggers": ["review niche targeting", "niche targeting", "target niche"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
)


def _category(subcategory: str) -> str:
    if subcategory in {"productivity"}:
        return "Automation & Productivity"
    if subcategory.startswith("project") or subcategory in {"team-ops", "goal-ops", "workflow-ops"}:
        return "Project Management"
    if subcategory == "company-ops":
        return "Company Building & Strategy"
    if subcategory.startswith("commerce") or subcategory in {"supplier-ops", "inventory-ops", "order-ops", "order-communications", "product-ops"}:
        return "E-commerce & Product"
    if subcategory == "growth-research":
        return "Lead Generation & Sales"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    approval_note = "Requires human approval before scheduling changes, publishing listings, syncing suppliers, auto-reordering, or sending shipment/customer updates."

    required_inputs = ["task_goal", "operating_context", "constraints"]
    optional_inputs = ["source_materials", "project_state", "commerce_context", "metrics", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to productivity, project ops, company ops, ecommerce, inventory, orders, or growth research.",
        "Do not invent task state, inventory, prices, supplier data, order status, or marketplace evidence.",
    ]
    if approval:
        when_not.append("Do not perform consequential side effects until a human explicitly approves the prepared plan, review, or draft.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior operator: ground work in supplied context, separate facts from assumptions, "
        "produce reviewable plans or reports, and never claim scheduling, commerce, supplier, order, or marketplace actions happened unless verified. "
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
        "maturity_level": "production_batch_6",
        "description": f"{spec['name']}: production-ready operating skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reports, reviews, or quality checks with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_productivity_project_commerce_or_growth_workflows",
            "escalate_when": ["low_confidence", "external_commerce_risk", "inventory_or_order_risk", "scheduling_or_customer_side_effect"],
        },
        "context_requirements": [
            "Relevant project, team, company, inventory, order, supplier, marketplace, or growth context must be supplied or discoverable.",
            "Approval boundaries and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"action_item_tracker", "project_progress_reporter", "mission_progress_tracker", "stock_monitoring_reporter"},
            "notes": "Use memory for prior operating decisions, project status, commerce constraints, and post-result summaries when useful.",
        },
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_external_delivery", "unapproved_account_change", "payment_execution", "auto_purchase", "unapproved_publish", "secret_exfiltration"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": approval_note if approval else "Planning, review, or research skill; still surface uncertainty, data gaps, and external-state assumptions.",
        "system_prompt": system_prompt,
        "developer_prompt": (
            "Respect AscendForge approval gates, auditability, safety, and tenant boundaries. "
            "For scheduling, listing automation, supplier sync, auto-reorder, customer updates, or external commerce work, prepare a reviewable artifact first. "
            "Include validation checks, blocked actions, and the smallest safe next step."
        ),
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with operating context {{operating_context}} and constraints {{constraints}}.",
        "internal_task_template": {"skill_id": spec["id"], "task_goal": "{{task_goal}}", "operating_context": "{{operating_context}}", "constraints": "{{constraints}}", "approval_required": approval},
        "examples": [f"Use {spec['name']} to {spec['triggers'][0]}.", f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps."],
        "quality_checklist": [
            "Uses real supplied or discoverable operating context.",
            "States assumptions, missing context, and blocked external actions.",
            "Separates artifact or findings, rationale, validation, risks, and next steps.",
            "Does not claim scheduling, supplier sync, listing, reorder, shipment, or marketplace actions unless verified.",
            "Applies approval gates for scheduling changes, commerce writes, supplier syncs, auto-reorders, and customer updates.",
        ],
        "success_criteria": [
            "Output is specific enough for a human or agent to review and execute.",
            "Project, team, company, inventory, order, supplier, marketplace, or growth risk is explicit.",
            "Verification or acceptance checks are included.",
        ],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "data_unverified", "external_state_unknown"],
        "fallback_strategy": "Return a partial result with assumptions, blocked actions, required approval, and the exact context needed to continue.",
        "audit_events": [f"skill.{spec['id']}.selected", f"skill.{spec['id']}.completed", f"skill.{spec['id']}.blocked"],
        "ui_metadata": {
            "visible": True,
            "wired": True,
            "dashboard_section": "skills",
            "batch": "batch_6",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "bronze",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 201,
        },
        "test_cases": [
            {"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}},
            {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing approval or operating context", "expected": {"status": "blocked_or_gap_reported"}},
        ],
        "documentation_status": "documented_batch_6",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-6", "production-skill", "operations"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "business-ops-agent", "commerce-agent"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing task state, inventory, order status, supplier data, or marketplace evidence.",
        },
        "output_format": {
            "sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what is checked, drafted, planned, blocked, and what remains unverified.",
        },
        "quality_standards": [
            "Grounded in real productivity, project, company, commerce, inventory, order, supplier, or growth context.",
            "Approval and audit boundaries respected.",
            "No fake schedule changes, supplier syncs, listings, reorders, shipments, or marketplace claims.",
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
            "Never bypass approval for scheduling, listing, supplier, order, inventory, customer, or external-commerce actions.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required operating context and report gaps.",
            "Prepare the plan, review, report, or quality check using allowed tools only.",
            "Apply approval and audit criteria before any consequential next action.",
            "Return artifact, validation, risk notes, approval needs, and next steps.",
        ],
        "source": "batch6_production_upgrade",
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
    data["_meta"]["batch6_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

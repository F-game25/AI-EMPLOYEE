#!/usr/bin/env python3
"""Upgrade the third 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "audience_strategy", "id": "growth_marketing_strategy_mapper", "name": "Growth Marketing Strategy Mapper", "subcategory": "growth-strategy", "triggers": ["map growth marketing strategy", "audience growth plan", "growth channel strategy"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "low"},
    {"replace": "seo_audit", "id": "seo_opportunity_auditor", "name": "SEO Opportunity Auditor", "subcategory": "seo", "triggers": ["audit seo opportunities", "seo gap analysis", "search visibility review"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "low"},
    {"replace": "technical_seo", "id": "technical_seo_checker", "name": "Technical SEO Checker", "subcategory": "seo", "triggers": ["check technical seo", "crawlability issue", "metadata seo"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "low"},
    {"replace": "google_ads_strategy", "id": "paid_ads_campaign_planner", "name": "Paid Ads Campaign Planner", "subcategory": "paid-ads", "triggers": ["plan paid ads campaign", "google ads strategy", "paid acquisition plan"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "ad_copy_creation", "id": "ad_copy_reviewer", "name": "Ad Copy Reviewer", "subcategory": "paid-ads", "triggers": ["review ad copy", "improve ad creative", "ad copy compliance"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "funnel_optimization", "id": "conversion_funnel_analyzer", "name": "Conversion Funnel Analyzer", "subcategory": "conversion", "triggers": ["analyze conversion funnel", "find funnel dropoffs", "conversion optimization"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "a_b_testing", "id": "ab_test_plan_builder", "name": "A/B Test Plan Builder", "subcategory": "experimentation", "triggers": ["build ab test plan", "a/b testing plan", "experiment design"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "brand_voice", "id": "brand_voice_guardian", "name": "Brand Voice Guardian", "subcategory": "brand", "triggers": ["check brand voice", "brand tone review", "voice consistency"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "multi_platform_posting", "id": "social_post_pipeline_planner", "name": "Social Post Pipeline Planner", "subcategory": "social-operations", "triggers": ["plan social post pipeline", "multi platform posting plan", "social content workflow"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "video_scripts", "id": "video_script_writer", "name": "Video Script Writer", "subcategory": "content-production", "triggers": ["write video script", "short video script", "script content"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "topic_research", "id": "topic_researcher", "name": "Topic Researcher", "subcategory": "research", "triggers": ["research topic", "topic brief", "content research"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "competitive_analysis", "id": "competitive_positioning_analyzer", "name": "Competitive Positioning Analyzer", "subcategory": "market-research", "triggers": ["competitive positioning", "competitor analysis", "market positioning"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "market_trend_analysis", "id": "market_trend_synthesizer", "name": "Market Trend Synthesizer", "subcategory": "market-research", "triggers": ["synthesize market trends", "market trend analysis", "trend research"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "research_synthesis", "id": "research_brief_synthesizer", "name": "Research Brief Synthesizer", "subcategory": "research", "triggers": ["synthesize research brief", "research summary", "source synthesis"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "executive_summary", "id": "executive_summary_writer", "name": "Executive Summary Writer", "subcategory": "reporting", "triggers": ["write executive summary", "summarize for leadership", "brief summary"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "daily_reports", "id": "daily_report_builder", "name": "Daily Report Builder", "subcategory": "reporting", "triggers": ["build daily report", "daily status report", "daily summary"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "financial_reporting", "id": "financial_report_reviewer", "name": "Financial Report Reviewer", "subcategory": "finance-reporting", "triggers": ["review financial report", "financial reporting quality", "finance report check"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "invoice_generation", "id": "invoice_draft_reviewer", "name": "Invoice Draft Reviewer", "subcategory": "finance-ops", "triggers": ["review invoice draft", "invoice quality check", "invoice preparation"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "payment_reminders", "id": "payment_followup_planner", "name": "Payment Followup Planner", "subcategory": "finance-ops", "triggers": ["plan payment followup", "payment reminder draft", "follow up unpaid invoice"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "expense_categorisation", "id": "expense_categorizer", "name": "Expense Categorizer", "subcategory": "finance-ops", "triggers": ["categorize expenses", "expense classification", "bookkeeping categories"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "tax_preparation", "id": "tax_prep_checklist_builder", "name": "Tax Prep Checklist Builder", "subcategory": "finance-compliance", "triggers": ["tax prep checklist", "prepare tax documents", "tax readiness"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "unit_economics", "id": "unit_economics_analyzer", "name": "Unit Economics Analyzer", "subcategory": "finance-analysis", "triggers": ["analyze unit economics", "margin per unit", "unit economics"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "budget_enforcement", "id": "budget_guardrail_planner", "name": "Budget Guardrail Planner", "subcategory": "finance-governance", "triggers": ["budget guardrails", "budget enforcement plan", "spend limits"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "job_description_writing", "id": "hiring_role_brief_writer", "name": "Hiring Role Brief Writer", "subcategory": "people-ops", "triggers": ["write hiring role brief", "job description brief", "role requirements"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "cv_screening", "id": "candidate_screening_assistant", "name": "Candidate Screening Assistant", "subcategory": "people-ops", "triggers": ["screen candidate", "candidate fit review", "cv screening"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "interview_frameworks", "id": "interview_plan_builder", "name": "Interview Plan Builder", "subcategory": "people-ops", "triggers": ["build interview plan", "interview framework", "candidate interview"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "onboarding_design", "id": "team_onboarding_planner", "name": "Team Onboarding Planner", "subcategory": "people-ops", "triggers": ["team onboarding plan", "new hire onboarding", "onboarding checklist"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "culture_design", "id": "culture_operating_principles_writer", "name": "Culture Operating Principles Writer", "subcategory": "people-ops", "triggers": ["write operating principles", "culture principles", "team norms"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "growth_okrs", "id": "okr_progress_reviewer", "name": "OKR Progress Reviewer", "subcategory": "planning", "triggers": ["review okr progress", "okr check", "goal progress"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "milestone_planning", "id": "milestone_plan_builder", "name": "Milestone Plan Builder", "subcategory": "planning", "triggers": ["build milestone plan", "milestone planning", "project milestones"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "stakeholder_management", "id": "stakeholder_update_writer", "name": "Stakeholder Update Writer", "subcategory": "project-communications", "triggers": ["write stakeholder update", "stakeholder status", "project update"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "raci_matrix", "id": "raci_matrix_builder", "name": "RACI Matrix Builder", "subcategory": "planning", "triggers": ["build raci matrix", "define responsibilities", "ownership matrix"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "standup_reports", "id": "standup_report_writer", "name": "Standup Report Writer", "subcategory": "project-communications", "triggers": ["write standup report", "daily standup summary", "team status"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "discord_notifications", "id": "discord_notification_planner", "name": "Discord Notification Planner", "subcategory": "notifications", "triggers": ["plan discord notification", "discord update draft", "notification copy"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "whatsapp_inbound", "id": "whatsapp_inbound_triager", "name": "WhatsApp Inbound Triager", "subcategory": "communications", "triggers": ["triage whatsapp inbound", "whatsapp message review", "inbound message classification"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "message_routing", "id": "message_routing_auditor", "name": "Message Routing Auditor", "subcategory": "communications", "triggers": ["audit message routing", "message routing rules", "communication routing"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "web_monitoring", "id": "web_monitoring_planner", "name": "Web Monitoring Planner", "subcategory": "monitoring", "triggers": ["plan web monitoring", "monitor web changes", "website watch plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "threat_intelligence", "id": "threat_intelligence_brief_writer", "name": "Threat Intelligence Brief Writer", "subcategory": "security-intelligence", "triggers": ["write threat intelligence brief", "threat intel summary", "security intelligence"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "tool_policy_gating", "id": "tool_policy_review_planner", "name": "Tool Policy Review Planner", "subcategory": "governance", "triggers": ["review tool policy", "tool policy gates", "policy review plan"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "token_budget_planning", "id": "token_budget_planner", "name": "Token Budget Planner", "subcategory": "resource-planning", "triggers": ["plan token budget", "token usage plan", "context budget"], "tools": ["read_file", "llm_infer"], "safety": "low"},
)


def _category(subcategory: str) -> str:
    if subcategory in {"growth-strategy", "seo", "paid-ads", "conversion", "experimentation", "brand", "social-operations", "content-production"}:
        return "Growth & Marketing"
    if subcategory in {"research", "market-research"}:
        return "Research & Analysis"
    if subcategory in {"reporting"}:
        return "Data Analysis"
    if subcategory.startswith("finance"):
        return "Finance & Investment"
    if subcategory == "people-ops":
        return "Company Building & Strategy"
    if subcategory in {"planning", "project-communications"}:
        return "Project Management"
    if subcategory in {"notifications", "communications"}:
        return "Communication Channels"
    if subcategory in {"monitoring", "security-intelligence", "governance"}:
        return "Security & Governance"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    tools = list(spec["tools"])
    approval_note = "Requires human approval before publishing, messaging, financial action, candidate decision, policy change, or external side effect."

    required_inputs = ["task_goal", "operating_context", "constraints"]
    optional_inputs = ["source_materials", "audience", "metrics", "budget", "deadline", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to growth, reporting, finance, people ops, planning, communications, monitoring, or governance.",
        "Do not invent metrics, financial records, candidate facts, market evidence, or external system state.",
    ]
    if approval:
        when_not.append("Do not perform consequential side effects until a human explicitly approves the prepared plan, draft, or decision aid.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior operator: ground work in supplied context, separate assumptions from facts, "
        "produce reviewable artifacts, and never claim external actions happened unless verified. "
        f"Primary triggers: {', '.join(spec['triggers'])}. Safety level: {safety}. "
        + (approval_note if approval else "Use read-only or planning-oriented behavior unless explicitly routed through an approved execution path.")
    )
    developer_prompt = (
        "Respect AscendForge approval gates, auditability, and tenant boundaries. "
        "For publishing, notifications, finance, hiring, monitoring, or policy-adjacent work, prepare a reviewable artifact first. "
        "Include validation checks, blocked actions, and the smallest safe next step."
    )

    return {
        **old,
        "id": spec["id"],
        "name": spec["name"],
        "category": _category(spec["subcategory"]),
        "subcategory": spec["subcategory"],
        "version": "1.0.0",
        "maturity_level": "production_batch_3",
        "description": f"{spec['name']}: production-ready operating skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, drafts, reviews, reports, or checks with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_business_finance_security_or_multi_step_workflows",
            "escalate_when": ["low_confidence", "financial_or_hiring_risk", "external_side_effect", "policy_or_security_boundary"],
        },
        "context_requirements": [
            "Relevant source, metric, market, finance, people, project, message, or policy context must be supplied or discoverable.",
            "Approval boundaries and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"daily_report_builder", "okr_progress_reviewer", "standup_report_writer", "token_budget_planner"},
            "notes": "Use memory for prior operating decisions, audience positioning, reporting patterns, project status, and post-result summaries when useful.",
        },
        "tools_allowed": tools,
        "tools_forbidden": ["unapproved_external_delivery", "unapproved_account_change", "payment_execution", "candidate_decision_automation", "secret_exfiltration", "mass_messaging"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": approval_note if approval else "Planning, research, or review skill; still surface uncertainty, data gaps, and policy-sensitive recommendations.",
        "system_prompt": system_prompt,
        "developer_prompt": developer_prompt,
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with operating context {{operating_context}} and constraints {{constraints}}.",
        "internal_task_template": {
            "skill_id": spec["id"],
            "task_goal": "{{task_goal}}",
            "operating_context": "{{operating_context}}",
            "constraints": "{{constraints}}",
            "approval_required": approval,
        },
        "examples": [
            f"Use {spec['name']} to {spec['triggers'][0]} for an AscendForge operating workflow.",
            f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps.",
        ],
        "quality_checklist": [
            "Uses real supplied or discoverable operating context.",
            "States assumptions, missing context, and blocked external actions.",
            "Separates artifact, rationale, validation, risks, and next steps.",
            "Does not claim publishing, messaging, financial, hiring, policy, or monitoring actions unless actually executed through approval.",
            "Applies approval gates for money, hiring, notifications, publishing, policy, account, and write-side effects.",
        ],
        "success_criteria": [
            "Output is specific enough for a human or agent to review and execute.",
            "Finance, hiring, brand, policy, security, or communications risk is explicit.",
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
            "batch": "batch_3",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "gold",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 81,
        },
        "test_cases": [
            {
                "name": f"selects_{spec['id']}",
                "input": spec["triggers"][0],
                "expected": {"selected_skill_id": spec["id"], "status": "selected"},
            },
            {
                "name": f"approval_or_gap_behavior_{spec['id']}",
                "input": "missing approval or operating context",
                "expected": {"status": "blocked_or_gap_reported"},
            },
        ],
        "documentation_status": "documented_batch_3",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-3", "production-skill", "operations"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "business-ops-agent", "money-mode-agent"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing operating context rather than inventing metrics, financial facts, candidate facts, or external state.",
        },
        "output_format": {
            "sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what is drafted, checked, planned, blocked, and what remains unverified.",
        },
        "quality_standards": [
            "Grounded in real operating or system context.",
            "Approval and audit boundaries respected.",
            "No fake integrations, metrics, financial actions, hiring decisions, notifications, or external delivery claims.",
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
            "Never bypass approval for money, hiring, messaging, publishing, policy, account, or credential actions.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required operating and system context and report gaps.",
            "Prepare the plan, draft, review, report, or check using allowed tools only.",
            "Apply approval and audit criteria before any consequential next action.",
            "Return artifact, validation, risk notes, approval needs, and next steps.",
        ],
        "source": "batch3_production_upgrade",
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
    data["_meta"]["batch3_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

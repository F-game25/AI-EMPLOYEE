#!/usr/bin/env python3
"""Upgrade the fifth 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "customer_service", "id": "customer_service_workflow_planner", "name": "Customer Service Workflow Planner", "subcategory": "customer-support-ops", "triggers": ["plan customer service workflow", "customer service process", "support workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "faq_handling", "id": "faq_knowledge_base_builder", "name": "FAQ Knowledge Base Builder", "subcategory": "customer-support-knowledge", "triggers": ["build faq knowledge base", "faq handling", "support knowledge base"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "ticket_tracking", "id": "support_ticket_tracker", "name": "Support Ticket Tracker", "subcategory": "customer-support-ops", "triggers": ["track support tickets", "ticket tracking", "support queue status"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "refund_processing", "id": "refund_case_reviewer", "name": "Refund Case Reviewer", "subcategory": "customer-support-risk", "triggers": ["review refund case", "refund processing review", "refund policy check"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "status_updates", "id": "customer_status_update_writer", "name": "Customer Status Update Writer", "subcategory": "customer-communications", "triggers": ["write customer status update", "customer status message", "support status update"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "customer_notification", "id": "customer_notification_approval_planner", "name": "Customer Notification Approval Planner", "subcategory": "customer-communications", "triggers": ["plan customer notification approval", "customer notification", "approval for customer message"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "lead_generation", "id": "lead_generation_campaign_planner", "name": "Lead Generation Campaign Planner", "subcategory": "sales-campaigns", "triggers": ["plan lead generation campaign", "lead generation plan", "new leads campaign"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "medium"},
    {"replace": "lead_hunting", "id": "lead_hunting_researcher", "name": "Lead Hunting Researcher", "subcategory": "sales-research", "triggers": ["research leads", "lead hunting", "find prospects"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "lead_enrichment", "id": "lead_enrichment_validator", "name": "Lead Enrichment Validator", "subcategory": "sales-data-quality", "triggers": ["validate lead enrichment", "lead data quality", "enriched lead check"], "tools": ["read_file", "web_search", "llm_infer"], "safety": "medium"},
    {"replace": "icp_matching", "id": "icp_match_score_reviewer", "name": "ICP Match Score Reviewer", "subcategory": "sales-qualification", "triggers": ["review icp match score", "icp matching", "ideal customer fit"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "icp_scoring", "id": "icp_scoring_model_reviewer", "name": "ICP Scoring Model Reviewer", "subcategory": "sales-qualification", "triggers": ["review icp scoring model", "icp scoring", "lead scoring criteria"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "cold_outreach", "id": "cold_outreach_risk_reviewer", "name": "Cold Outreach Risk Reviewer", "subcategory": "outreach-safety", "triggers": ["review cold outreach risk", "cold outreach compliance", "outreach risk"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "cold_email_writing", "id": "cold_email_draft_reviewer", "name": "Cold Email Draft Reviewer", "subcategory": "outreach-safety", "triggers": ["review cold email draft", "cold email writing", "outreach email review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "cold_email_sequences", "id": "cold_email_sequence_planner", "name": "Cold Email Sequence Planner", "subcategory": "outreach-safety", "triggers": ["plan cold email sequence", "cold email sequences", "outreach cadence"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "email_deliverability", "id": "email_deliverability_checker", "name": "Email Deliverability Checker", "subcategory": "email-operations", "triggers": ["check email deliverability", "deliverability risk", "email sending health"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "email_campaigns", "id": "email_campaign_approval_planner", "name": "Email Campaign Approval Planner", "subcategory": "email-operations", "triggers": ["plan email campaign approval", "email campaign review", "campaign send approval"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "open_rate_optimisation", "id": "open_rate_experiment_analyzer", "name": "Open Rate Experiment Analyzer", "subcategory": "email-operations", "triggers": ["analyze open rate experiment", "open rate optimization", "email experiment"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "sales_forecasting", "id": "sales_forecast_reviewer", "name": "Sales Forecast Reviewer", "subcategory": "sales-forecasting", "triggers": ["review sales forecast", "sales forecasting", "pipeline forecast"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "pipeline_management", "id": "sales_pipeline_health_checker", "name": "Sales Pipeline Health Checker", "subcategory": "sales-operations", "triggers": ["check sales pipeline health", "pipeline management", "sales pipeline review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "spam_analysis", "id": "spam_risk_analyzer", "name": "Spam Risk Analyzer", "subcategory": "outreach-safety", "triggers": ["analyze spam risk", "spam analysis", "deliverability compliance"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "content_strategy", "id": "content_strategy_brief_builder", "name": "Content Strategy Brief Builder", "subcategory": "content-strategy", "triggers": ["build content strategy brief", "content strategy", "content plan brief"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "copywriting_expert", "id": "copywriting_quality_reviewer", "name": "Copywriting Quality Reviewer", "subcategory": "content-quality", "triggers": ["review copywriting quality", "copywriting review", "copy quality"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "sales_copy", "id": "sales_copy_reviewer", "name": "Sales Copy Reviewer", "subcategory": "content-quality", "triggers": ["review sales copy", "sales copy", "conversion copy review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "script_writing", "id": "script_outline_builder", "name": "Script Outline Builder", "subcategory": "content-production", "triggers": ["build script outline", "script writing", "video script outline"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "voiceover_generation", "id": "voiceover_script_reviewer", "name": "Voiceover Script Reviewer", "subcategory": "content-production", "triggers": ["review voiceover script", "voiceover generation", "voiceover copy"], "tools": ["read_file", "llm_infer"], "safety": "medium", "approval": True},
    {"replace": "image_prompt_generation", "id": "image_prompt_quality_reviewer", "name": "Image Prompt Quality Reviewer", "subcategory": "creative-direction", "triggers": ["review image prompt quality", "image prompt generation", "visual prompt quality"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "visual_prompts", "id": "visual_prompt_art_director", "name": "Visual Prompt Art Director", "subcategory": "creative-direction", "triggers": ["direct visual prompt", "visual prompts", "art direction prompt"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "design_system_creation", "id": "design_system_auditor", "name": "Design System Auditor", "subcategory": "design-quality", "triggers": ["audit design system", "design system creation", "component style review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "responsive_layout", "id": "responsive_layout_checker", "name": "Responsive Layout Checker", "subcategory": "design-quality", "triggers": ["check responsive layout", "responsive layout", "mobile layout audit"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "ui_audit", "id": "ui_quality_issue_finder", "name": "UI Quality Issue Finder", "subcategory": "design-quality", "triggers": ["find ui quality issues", "ui audit", "interface quality"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "market_monitoring", "id": "market_monitoring_brief_builder", "name": "Market Monitoring Brief Builder", "subcategory": "market-intelligence", "triggers": ["build market monitoring brief", "market monitoring", "market watch summary"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "signal_aggregation", "id": "trading_signal_aggregator", "name": "Trading Signal Aggregator", "subcategory": "trading-research", "triggers": ["aggregate trading signals", "signal aggregation", "market signals"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "signal_generation", "id": "trading_signal_quality_reviewer", "name": "Trading Signal Quality Reviewer", "subcategory": "trading-research", "triggers": ["review trading signal quality", "signal generation", "trading signal review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "backtesting", "id": "backtest_plan_reviewer", "name": "Backtest Plan Reviewer", "subcategory": "trading-research", "triggers": ["review backtest plan", "backtesting", "trading backtest"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "portfolio_tracking", "id": "portfolio_tracking_reporter", "name": "Portfolio Tracking Reporter", "subcategory": "finance-research", "triggers": ["report portfolio tracking", "portfolio tracking", "portfolio status"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "portfolio_optimization", "id": "portfolio_optimization_risk_reviewer", "name": "Portfolio Optimization Risk Reviewer", "subcategory": "finance-research", "triggers": ["review portfolio optimization risk", "portfolio optimization", "portfolio risk"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "financial_analysis", "id": "financial_analysis_brief_builder", "name": "Financial Analysis Brief Builder", "subcategory": "finance-research", "triggers": ["build financial analysis brief", "financial analysis", "finance research brief"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "web_search", "id": "web_search_plan_builder", "name": "Web Search Plan Builder", "subcategory": "research-workflow", "triggers": ["build web search plan", "web search", "research query plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "web_fetch", "id": "web_fetch_safety_reviewer", "name": "Web Fetch Safety Reviewer", "subcategory": "research-workflow", "triggers": ["review web fetch safety", "web fetch", "fetch external source"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "fact_verification", "id": "fact_checking_workflow_runner", "name": "Fact Checking Workflow Runner", "subcategory": "research-quality", "triggers": ["run fact checking workflow", "fact verification", "verify claims"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
)


def _category(subcategory: str) -> str:
    if subcategory.startswith("customer"):
        return "Customer Support"
    if subcategory.startswith("sales") or subcategory in {"outreach-safety", "email-operations"}:
        return "Lead Generation & Sales"
    if subcategory.startswith("content") or subcategory == "creative-direction":
        return "Content & Writing"
    if subcategory == "design-quality":
        return "Branding & Identity"
    if subcategory in {"market-intelligence", "research-workflow", "research-quality"}:
        return "Research & Analysis"
    if subcategory in {"trading-research", "finance-research"}:
        return "Finance & Investment"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    approval_note = "Requires human approval before contacting customers or leads, sending campaigns, issuing refunds, publishing content, or taking financial/trading action."

    required_inputs = ["task_goal", "operating_context", "constraints"]
    optional_inputs = ["source_materials", "customer_context", "audience", "examples", "metrics", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to support, sales, outreach, content, design, market research, finance, or web research.",
        "Do not invent customer facts, lead data, financial records, market signals, source evidence, or external outcomes.",
    ]
    if approval:
        when_not.append("Do not perform consequential side effects until a human explicitly approves the prepared review, draft, or plan.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior operator: ground work in supplied context, separate facts from assumptions, "
        "produce reviewable artifacts, and never claim customer, outreach, refund, publishing, or financial actions happened unless verified. "
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
        "maturity_level": "production_batch_5",
        "description": f"{spec['name']}: production-ready operating skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reviews, briefs, or quality checks with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_customer_sales_content_finance_or_research_workflows",
            "escalate_when": ["low_confidence", "customer_or_outreach_risk", "financial_or_trading_risk", "external_source_uncertainty"],
        },
        "context_requirements": [
            "Relevant customer, lead, content, design, market, finance, source, or workflow context must be supplied or discoverable.",
            "Approval boundaries and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"support_ticket_tracker", "sales_pipeline_health_checker", "portfolio_tracking_reporter", "fact_checking_workflow_runner"},
            "notes": "Use memory for prior customer decisions, outreach constraints, content standards, research lessons, and post-result summaries when useful.",
        },
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_external_delivery", "mass_messaging", "payment_execution", "refund_execution", "trading_execution", "secret_exfiltration", "unapproved_publish"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": approval_note if approval else "Planning, review, or research skill; still surface uncertainty, data gaps, and policy-sensitive recommendations.",
        "system_prompt": system_prompt,
        "developer_prompt": (
            "Respect AscendForge approval gates, auditability, safety, and tenant boundaries. "
            "For customer communication, outreach, campaigns, refunds, content publishing, financial analysis, or trading-adjacent work, prepare a reviewable artifact first. "
            "Include validation checks, blocked actions, compliance notes, and the smallest safe next step."
        ),
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
            "Separates artifact or findings, rationale, validation, risks, and next steps.",
            "Does not claim messages, refunds, publishes, trades, or external research conclusions unless verified.",
            "Applies approval gates for customer contact, outreach, campaigns, refunds, publishing, and financial/trading actions.",
        ],
        "success_criteria": [
            "Output is specific enough for a human or agent to review and execute.",
            "Customer, outreach, content, finance, trading, or source-quality risk is explicit.",
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
            "batch": "batch_5",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "gold",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 161,
        },
        "test_cases": [
            {"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}},
            {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing approval or operating context", "expected": {"status": "blocked_or_gap_reported"}},
        ],
        "documentation_status": "documented_batch_5",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-5", "production-skill", "operations"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "business-ops-agent", "research-agent"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing customer facts, lead data, market signals, financial records, or source evidence.",
        },
        "output_format": {
            "sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what is checked, drafted, planned, blocked, and what remains unverified.",
        },
        "quality_standards": [
            "Grounded in real customer, sales, content, design, finance, or research context.",
            "Approval and audit boundaries respected.",
            "No fake customer actions, outreach sends, refunds, publishes, trades, or source claims.",
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
            "Never bypass approval for customer contact, outreach, refund, campaign, publishing, financial, or trading actions.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required operating context and report gaps.",
            "Prepare the plan, review, brief, or quality check using allowed tools only.",
            "Apply approval and audit criteria before any consequential next action.",
            "Return artifact, validation, risk notes, approval needs, and next steps.",
        ],
        "source": "batch5_production_upgrade",
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
    data["_meta"]["batch5_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

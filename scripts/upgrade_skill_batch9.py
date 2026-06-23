#!/usr/bin/env python3
"""Upgrade the ninth 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "lesson_writing", "id": "lesson_content_writer", "name": "Lesson Content Writer", "subcategory": "education-content", "triggers": ["write lesson content", "lesson writing", "course lesson draft"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "linkedin_optimization", "id": "linkedin_profile_optimization_reviewer", "name": "LinkedIn Profile Optimization Reviewer", "subcategory": "social-profile", "triggers": ["review linkedin profile optimization", "linkedin optimization", "linkedin profile improvements"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "list_segmentation", "id": "list_segmentation_planner", "name": "List Segmentation Planner", "subcategory": "email-growth", "triggers": ["plan list segmentation", "list segmentation", "email audience segments"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "market_entry_strategy", "id": "market_entry_strategy_reviewer", "name": "Market Entry Strategy Reviewer", "subcategory": "strategy-ops", "triggers": ["review market entry strategy", "market entry strategy", "go to market entry plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "market_positioning", "id": "market_positioning_reviewer", "name": "Market Positioning Reviewer", "subcategory": "brand-strategy", "triggers": ["review market positioning", "market positioning", "positioning analysis"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "message_performance_tracking", "id": "message_performance_tracking_reporter", "name": "Message Performance Tracking Reporter", "subcategory": "analytics", "triggers": ["report message performance tracking", "message performance tracking", "messaging metrics"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "messaging_framework", "id": "messaging_framework_reviewer", "name": "Messaging Framework Reviewer", "subcategory": "brand-strategy", "triggers": ["review messaging framework", "messaging framework", "brand messaging pillars"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "meta_ads_strategy", "id": "meta_ads_strategy_reviewer", "name": "Meta Ads Strategy Reviewer", "subcategory": "paid-media", "triggers": ["review meta ads strategy", "meta ads strategy", "facebook ads plan"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "mitigation_planning", "id": "risk_mitigation_plan_builder", "name": "Risk Mitigation Plan Builder", "subcategory": "risk-ops", "triggers": ["build risk mitigation plan", "mitigation planning", "risk mitigation steps"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "notifications", "id": "notification_dispatch_reviewer", "name": "Notification Dispatch Reviewer", "subcategory": "comms-automation", "triggers": ["review notification dispatch", "notifications", "outbound notification policy"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "order_aggregation", "id": "order_aggregation_reconciler", "name": "Order Aggregation Reconciler", "subcategory": "ops-commerce", "triggers": ["reconcile order aggregation", "order aggregation", "aggregate orders"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "outreach_sequencing", "id": "outreach_sequence_reviewer", "name": "Outreach Sequence Reviewer", "subcategory": "sales-ops", "triggers": ["review outreach sequence", "outreach sequencing", "cold outreach cadence"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "performance_diagnosis", "id": "performance_diagnosis_analyst", "name": "Performance Diagnosis Analyst", "subcategory": "analytics", "triggers": ["diagnose performance issues", "performance diagnosis", "campaign performance diagnosis"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "performance_prediction", "id": "performance_prediction_reviewer", "name": "Performance Prediction Reviewer", "subcategory": "analytics", "triggers": ["review performance prediction", "performance prediction", "forecast performance"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "performance_tracking", "id": "performance_tracking_reporter", "name": "Performance Tracking Reporter", "subcategory": "analytics", "triggers": ["report performance tracking", "performance tracking", "kpi tracking report"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "persona_creation", "id": "buyer_persona_builder", "name": "Buyer Persona Builder", "subcategory": "marketing-research", "triggers": ["build buyer persona", "persona creation", "customer persona"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "plg_strategy", "id": "plg_strategy_reviewer", "name": "PLG Strategy Reviewer", "subcategory": "growth-experiments", "triggers": ["review plg strategy", "plg strategy", "product led growth plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "ppc_campaign_architecture", "id": "ppc_campaign_architecture_reviewer", "name": "PPC Campaign Architecture Reviewer", "subcategory": "paid-media", "triggers": ["review ppc campaign architecture", "ppc campaign architecture", "paid search structure"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "prediction_market_analysis", "id": "prediction_market_analysis_brief_builder", "name": "Prediction Market Analysis Brief Builder", "subcategory": "finance-research", "triggers": ["build prediction market analysis brief", "prediction market analysis", "prediction market edge"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "price_prediction", "id": "price_prediction_review_brief_builder", "name": "Price Prediction Review Brief Builder", "subcategory": "finance-research", "triggers": ["build price prediction review brief", "price prediction", "price forecast review"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "profit_margin_calc", "id": "profit_margin_calculation_reviewer", "name": "Profit Margin Calculation Reviewer", "subcategory": "ops-finance", "triggers": ["review profit margin calculation", "profit margin calc", "margin analysis"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "prospect_research", "id": "prospect_research_brief_builder", "name": "Prospect Research Brief Builder", "subcategory": "sales-research", "triggers": ["build prospect research brief", "prospect research", "account research"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "quiz_generation", "id": "quiz_content_builder", "name": "Quiz Content Builder", "subcategory": "content-ops", "triggers": ["build quiz content", "quiz generation", "lead quiz"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "report_generation", "id": "report_generation_reviewer", "name": "Report Generation Reviewer", "subcategory": "document-ops", "triggers": ["review report generation", "report generation", "generated report quality"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "rss_fetching", "id": "rss_feed_fetch_plan_builder", "name": "RSS Feed Fetch Plan Builder", "subcategory": "search-research", "triggers": ["build rss feed fetch plan", "rss fetching", "rss source plan"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "scene_extraction", "id": "scene_extraction_reviewer", "name": "Scene Extraction Reviewer", "subcategory": "media-content", "triggers": ["review scene extraction", "scene extraction", "video scene breakdown"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "schema_markup", "id": "schema_markup_reviewer", "name": "Schema Markup Reviewer", "subcategory": "seo", "triggers": ["review schema markup", "schema markup", "structured data review"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "scripting", "id": "content_script_writer", "name": "Content Script Writer", "subcategory": "content-ops", "triggers": ["write content script", "scripting", "video or audio script"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "self_improvement", "id": "self_improvement_proposal_reviewer", "name": "Self-Improvement Proposal Reviewer", "subcategory": "autonomy-ops", "triggers": ["review self improvement proposal", "self improvement", "system self improvement plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "seo_optimization", "id": "seo_optimization_reviewer", "name": "SEO Optimization Reviewer", "subcategory": "seo", "triggers": ["review seo optimization", "seo optimization", "on page seo review"], "tools": ["read_file", "browser_inspect", "llm_infer"], "safety": "low"},
    {"replace": "smart_contract_parameters", "id": "smart_contract_parameter_reviewer", "name": "Smart Contract Parameter Reviewer", "subcategory": "web3-engineering", "triggers": ["review smart contract parameters", "smart contract parameters", "contract config review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "storytelling", "id": "brand_storytelling_reviewer", "name": "Brand Storytelling Reviewer", "subcategory": "brand-strategy", "triggers": ["review brand storytelling", "storytelling", "narrative review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "strategic_analysis", "id": "strategic_analysis_brief_builder", "name": "Strategic Analysis Brief Builder", "subcategory": "strategy-ops", "triggers": ["build strategic analysis brief", "strategic analysis", "strategy analysis"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "medium"},
    {"replace": "subscriber_management", "id": "subscriber_management_reviewer", "name": "Subscriber Management Reviewer", "subcategory": "email-growth", "triggers": ["review subscriber management", "subscriber management", "email list hygiene"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "swarm_simulation", "id": "swarm_simulation_plan_reviewer", "name": "Swarm Simulation Plan Reviewer", "subcategory": "autonomy-sim", "triggers": ["review swarm simulation plan", "swarm simulation", "multi agent simulation"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "thought_leadership", "id": "thought_leadership_content_reviewer", "name": "Thought Leadership Content Reviewer", "subcategory": "social-content", "triggers": ["review thought leadership content", "thought leadership", "thought leadership post"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "tiktok_scripting", "id": "tiktok_script_writer", "name": "TikTok Script Writer", "subcategory": "social-content", "triggers": ["write tiktok script", "tiktok scripting", "short video script"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "tiktok_trend_scanning", "id": "tiktok_trend_scan_reporter", "name": "TikTok Trend Scan Reporter", "subcategory": "social-research", "triggers": ["report tiktok trend scan", "tiktok trend scanning", "trending tiktok formats"], "tools": ["web_search", "read_file", "llm_infer"], "safety": "low"},
    {"replace": "touchpoint_mapping", "id": "customer_touchpoint_map_builder", "name": "Customer Touchpoint Map Builder", "subcategory": "marketing-ops", "triggers": ["build customer touchpoint map", "touchpoint mapping", "customer journey touchpoints"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "trading_bot_coding", "id": "trading_bot_code_reviewer", "name": "Trading Bot Code Reviewer", "subcategory": "trading-engineering", "triggers": ["review trading bot code", "trading bot coding", "automated trading logic review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
)


def _category(subcategory: str) -> str:
    if subcategory in {"email-growth", "brand-strategy", "paid-media", "growth-experiments", "marketing-ops"}:
        return "Growth & Marketing"
    if subcategory in {"analytics"}:
        return "Data Analysis"
    if subcategory in {"finance-research", "ops-finance"}:
        return "Finance & Investment"
    if subcategory in {"sales-ops", "sales-research", "email-infra"}:
        return "Lead Generation & Sales"
    if subcategory in {"document-ops", "autonomy-ops", "autonomy-sim"}:
        return "Automation & Productivity"
    if subcategory in {"marketing-research", "search-research", "social-research"}:
        return "Research & Analysis"
    if subcategory in {"education-content", "content-ops", "media-content"}:
        return "Content & Writing"
    if subcategory in {"social-profile", "social-content"}:
        return "Social Media"
    if subcategory in {"seo"}:
        return "Marketing & SEO"
    if subcategory in {"strategy-ops", "risk-ops"}:
        return "Company Building & Strategy"
    if subcategory in {"comms-automation"}:
        return "Communication Channels"
    if subcategory in {"ops-commerce"}:
        return "E-commerce & Product"
    if subcategory in {"web3-engineering"}:
        return "Crypto & Web3"
    if subcategory in {"trading-engineering"}:
        return "Trading & Finance"
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
    approval_note = "Requires human approval before external outreach, notification/messaging delivery, trading/investment or on-chain actions, content publication, or any customer-facing delivery."
    when_not = [
        "Do not use when the request is unrelated to growth, content, brand, sales, analytics, research, finance, or engineering review.",
        "Do not invent analytics, audience data, brand rules, market evidence, on-chain state, or delivery outcomes.",
    ]
    if approval:
        when_not.append("Do not send, publish, automate, trade, or contact anyone until a human approves the prepared artifact.")
    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior go-to-market, brand, content, research, finance, and engineering reviewer: ground work in supplied "
        "context, mark missing evidence, produce reviewable artifacts, and never claim publication, delivery, trade execution, or "
        "analytics verification unless proven. "
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
        "maturity_level": "production_batch_9",
        "description": f"{spec['name']}: production-ready skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded plans, reviews, briefs, checklists, or quality gates.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {"minimum": "local_reasoning_model_or_cloud_fallback", "preferred": "strong_reasoning_for_growth_brand_research_finance_and_engineering_workflows", "escalate_when": ["low_confidence", "external_delivery_requested", "regulated_or_financial_claims", "audience_or_brand_context_missing"]},
        "context_requirements": ["Relevant audience, brand, campaign, analytics, research, finance, or engineering context must be supplied or discoverable.", "Approval boundaries and delivery/execution channel must be explicit for customer-facing, messaging, trading, or on-chain work."],
        "memory_usage": {"read": True, "write": False, "notes": "Use memory for prior brand rules, campaign decisions, and accepted operating assumptions; do not write unless routed through an approved memory skill."},
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_publish", "unapproved_outreach", "unapproved_notification_send", "unapproved_trading_execution", "unapproved_onchain_action", "secret_exfiltration", "fabricated_metrics"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe",
        "approval_policy": "human_approval_required_for_external_delivery" if approval else "read_or_plan_without_external_side_effects",
        "risk_notes": approval_note if approval else "Planning or review skill; still surface uncertainty, missing evidence, and customer-facing or financial risk.",
        "system_prompt": system_prompt,
        "developer_prompt": "Respect AscendForge approval gates, auditability, tenant boundaries, and Money Mode delivery rules. Prepare reviewable artifacts first; never publish, contact, send notifications, trade, or take on-chain actions without approval.",
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with context {{audience_or_system_context}} and constraints {{constraints}}.",
        "internal_task_template": {"skill_id": spec["id"], "task_goal": "{{task_goal}}", "audience_or_system_context": "{{audience_or_system_context}}", "constraints": "{{constraints}}", "approval_required": approval},
        "examples": [f"Use {spec['name']} to {spec['triggers'][0]}.", f"Run {spec['name']} and return artifact, assumptions, risks, approval needs, and validation steps."],
        "quality_checklist": ["Uses supplied brand, audience, campaign, analytics, research, finance, or engineering context.", "States assumptions and missing evidence.", "Separates artifact, rationale, validation, risks, approval needs, and next steps.", "Does not claim publication, outreach, notification delivery, trade execution, on-chain action, or analytics results without proof.", "Applies approval gates for customer-facing, messaging, content publication, financial, and trading outputs."],
        "success_criteria": ["Output is specific enough for review or execution by an approved operator.", "Messaging, brand, analytics, financial, or operational risk is explicit.", "Verification or acceptance checks are included."],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "unverified_metrics", "policy_boundary"],
        "fallback_strategy": "Return a partial artifact with assumptions, blocked delivery actions, required approval, and exact context needed to continue.",
        "audit_events": [f"skill.{spec['id']}.selected", f"skill.{spec['id']}.completed", f"skill.{spec['id']}.blocked"],
        "ui_metadata": {"visible": True, "wired": True, "dashboard_section": "skills", "batch": "batch_9", "status": "production_ready", "icon": "send" if approval else "chart", "accent": "gold", "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 321},
        "test_cases": [{"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}}, {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing audience or approval context", "expected": {"status": "blocked_or_gap_reported"}}],
        "documentation_status": "documented_batch_9",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return artifact, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-9", "production-skill", "go-to-market"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "money-agent", "growth-agent"}),
        "input_format": {"required_fields": required_inputs, "optional_fields": optional_inputs, "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing metrics, delivery results, or brand evidence."},
        "output_format": {"sections": ["artifact", "assumptions", "validation", "risks", "approval_needs", "next_steps"], "format": "structured_markdown", "output_contract": "Every output must show what is drafted, reviewed, planned, blocked, and unverified."},
        "quality_standards": ["Grounded in real brand, audience, campaign, analytics, research, finance, or engineering context.", "Approval and audit boundaries respected.", "No fake delivery, publication, analytics, outreach, trade, or on-chain action claims.", f"{spec['name']} passes its production quality checklist."],
        "error_handling": {"retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"], "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "unverified_external_state"], "fallback_strategy": "Return a gap report with the smallest safe next step."},
        "best_practices": ["Inspect supplied context before drafting or recommending action.", "Use existing approval, audit, and skill routing contracts.", "Keep outputs structured, reviewable, and verifiable.", "Never bypass approval for customer-facing, messaging, content publication, financial, trading, or on-chain actions."],
        "execution_steps": [f"Classify whether {spec['name']} is the right skill for the goal.", "Collect required context and report gaps.", "Prepare the plan, review, brief, checklist, or quality gate using allowed tools only.", "Apply approval and audit criteria before external delivery.", "Return artifact, validation, risk notes, approval needs, and next steps."],
        "source": "batch9_production_upgrade",
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
    data["_meta"]["batch9_production_upgrade"] = {"count": len(REPLACEMENTS), "mode": "canonical_replacements_preserve_total", "total_skills_preserved": len(skills)}
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

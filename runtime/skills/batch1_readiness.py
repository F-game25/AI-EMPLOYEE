"""Readiness checks for the first production skill batch."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BATCH1_SKILL_IDS: tuple[str, ...] = (
    "codebase_reader",
    "architecture_mapper",
    "bug_finder",
    "error_trace_analyzer",
    "refactor_planner",
    "secure_code_reviewer",
    "test_generator",
    "ui_ux_auditor",
    "api_route_inspector",
    "database_schema_analyzer",
    "agent_task_planner",
    "agent_task_decomposer",
    "local_file_reader",
    "local_file_writer",
    "browser_research_skill",
    "source_credibility_checker",
    "documentation_writer",
    "implementation_plan_writer",
    "prompt_optimizer",
    "context_compressor",
    "memory_linker",
    "model_router_evaluator",
    "llm_output_judge",
    "failure_forensics_analyzer",
    "regression_detector",
    "sandbox_test_runner",
    "security_threat_modeler",
    "dependency_vulnerability_checker",
    "command_safety_classifier",
    "human_approval_gate_planner",
    "remote_compute_planner",
    "resource_usage_optimizer",
    "system_startup_diagnostics",
    "frontend_build_checker",
    "backend_health_checker",
    "python_service_health_checker",
    "ollama_model_checker",
    "skill_registry_validator",
    "dashboard_skill_sync_checker",
    "end_to_end_task_executor",
)

BATCH2_SKILL_IDS: tuple[str, ...] = (
    "opportunity_scanner",
    "paid_task_evaluator",
    "client_brief_analyzer",
    "proposal_writer",
    "quote_builder",
    "scope_risk_assessor",
    "deliverable_packager",
    "client_delivery_reviewer",
    "earnings_tracker",
    "money_feedback_analyzer",
    "lead_source_finder",
    "icp_researcher",
    "prospect_qualifier",
    "outreach_sequence_planner",
    "email_personalizer",
    "crm_update_planner",
    "content_pipeline_planner",
    "content_quality_reviewer",
    "publish_approval_planner",
    "affiliate_offer_evaluator",
    "ecommerce_product_validator",
    "supplier_risk_checker",
    "order_workflow_auditor",
    "inventory_signal_analyzer",
    "marketplace_listing_optimizer",
    "customer_support_triager",
    "support_response_reviewer",
    "meeting_summary_writer",
    "calendar_schedule_planner",
    "workflow_template_builder",
    "automation_runbook_writer",
    "integration_health_checker",
    "api_key_rotation_planner",
    "secrets_exposure_checker",
    "tenant_isolation_checker",
    "audit_log_reviewer",
    "cost_roi_calculator",
    "product_dashboard_metric_mapper",
    "agent_performance_reviewer",
    "learning_dataset_curator",
)

BATCH3_SKILL_IDS: tuple[str, ...] = (
    "growth_marketing_strategy_mapper",
    "seo_opportunity_auditor",
    "technical_seo_checker",
    "paid_ads_campaign_planner",
    "ad_copy_reviewer",
    "conversion_funnel_analyzer",
    "ab_test_plan_builder",
    "brand_voice_guardian",
    "social_post_pipeline_planner",
    "video_script_writer",
    "topic_researcher",
    "competitive_positioning_analyzer",
    "market_trend_synthesizer",
    "research_brief_synthesizer",
    "executive_summary_writer",
    "daily_report_builder",
    "financial_report_reviewer",
    "invoice_draft_reviewer",
    "payment_followup_planner",
    "expense_categorizer",
    "tax_prep_checklist_builder",
    "unit_economics_analyzer",
    "budget_guardrail_planner",
    "hiring_role_brief_writer",
    "candidate_screening_assistant",
    "interview_plan_builder",
    "team_onboarding_planner",
    "culture_operating_principles_writer",
    "okr_progress_reviewer",
    "milestone_plan_builder",
    "stakeholder_update_writer",
    "raci_matrix_builder",
    "standup_report_writer",
    "discord_notification_planner",
    "whatsapp_inbound_triager",
    "message_routing_auditor",
    "web_monitoring_planner",
    "threat_intelligence_brief_writer",
    "tool_policy_review_planner",
    "token_budget_planner",
)

BATCH4_SKILL_IDS: tuple[str, ...] = (
    "api_integration_contract_tester",
    "shopify_webhook_auditor",
    "shopify_inventory_sync_checker",
    "shopify_publish_approval_planner",
    "stripe_data_ingestion_checker",
    "quickbooks_sync_reconciler",
    "email_platform_integration_checker",
    "twilio_integration_checker",
    "discord_integration_checker",
    "cross_channel_notification_planner",
    "data_extraction_planner",
    "data_export_validator",
    "csv_output_validator",
    "batch_job_planner",
    "cron_schedule_auditor",
    "backup_readiness_checker",
    "archive_retention_planner",
    "deployment_state_tracker",
    "rollback_plan_reviewer",
    "patch_rollout_planner",
    "release_versioning_checker",
    "changelog_writer",
    "diagnostic_report_builder",
    "anomaly_alert_rule_planner",
    "system_status_reporter",
    "agent_coordination_planner",
    "agent_selection_evaluator",
    "agent_dispatch_auditor",
    "agent_composition_designer",
    "bot_lifecycle_manager",
    "state_snapshot_aggregator",
    "multi_agent_result_synthesizer",
    "multi_agent_coordination_reviewer",
    "multi_agent_synthesis_reviewer",
    "provider_fallback_planner",
    "session_persistence_checker",
    "vault_index_health_checker",
    "vault_retrieval_quality_checker",
    "trigger_rule_auditor",
    "template_quality_scorer",
)

BATCH5_SKILL_IDS: tuple[str, ...] = (
    "customer_service_workflow_planner",
    "faq_knowledge_base_builder",
    "support_ticket_tracker",
    "refund_case_reviewer",
    "customer_status_update_writer",
    "customer_notification_approval_planner",
    "lead_generation_campaign_planner",
    "lead_hunting_researcher",
    "lead_enrichment_validator",
    "icp_match_score_reviewer",
    "icp_scoring_model_reviewer",
    "cold_outreach_risk_reviewer",
    "cold_email_draft_reviewer",
    "cold_email_sequence_planner",
    "email_deliverability_checker",
    "email_campaign_approval_planner",
    "open_rate_experiment_analyzer",
    "sales_forecast_reviewer",
    "sales_pipeline_health_checker",
    "spam_risk_analyzer",
    "content_strategy_brief_builder",
    "copywriting_quality_reviewer",
    "sales_copy_reviewer",
    "script_outline_builder",
    "voiceover_script_reviewer",
    "image_prompt_quality_reviewer",
    "visual_prompt_art_director",
    "design_system_auditor",
    "responsive_layout_checker",
    "ui_quality_issue_finder",
    "market_monitoring_brief_builder",
    "trading_signal_aggregator",
    "trading_signal_quality_reviewer",
    "backtest_plan_reviewer",
    "portfolio_tracking_reporter",
    "portfolio_optimization_risk_reviewer",
    "financial_analysis_brief_builder",
    "web_search_plan_builder",
    "web_fetch_safety_reviewer",
    "fact_checking_workflow_runner",
)

BATCH6_SKILL_IDS: tuple[str, ...] = (
    "action_item_tracker",
    "meeting_note_structurer",
    "transcript_insight_extractor",
    "schedule_conflict_planner",
    "gantt_timeline_reviewer",
    "work_breakdown_builder",
    "project_progress_reporter",
    "retrospective_action_planner",
    "team_coordination_brief_builder",
    "task_assignment_reviewer",
    "task_schedule_optimizer",
    "goal_health_reviewer",
    "goal_decomposition_reviewer",
    "workflow_design_reviewer",
    "workflow_generation_planner",
    "workflow_management_auditor",
    "company_operating_system_mapper",
    "mission_progress_tracker",
    "org_hierarchy_mapper",
    "reporting_line_reviewer",
    "workload_balance_checker",
    "amazon_product_researcher",
    "marketplace_competition_analyzer",
    "listing_automation_planner",
    "supplier_api_contract_reviewer",
    "supplier_api_sync_checker",
    "low_stock_alert_planner",
    "auto_reorder_policy_reviewer",
    "order_routing_rule_auditor",
    "order_tracking_status_reporter",
    "shipment_tracking_update_writer",
    "price_comparison_researcher",
    "price_monitoring_rule_planner",
    "stock_monitoring_reporter",
    "ecommerce_trend_detector",
    "trend_spotting_brief_builder",
    "top_product_ranking_reviewer",
    "product_design_brief_reviewer",
    "customer_segment_analyzer",
    "niche_targeting_reviewer",
)

BATCH7_SKILL_IDS: tuple[str, ...] = (
    "agent_memory_health_checker",
    "skill_generation_planner",
    "ai_ml_implementation_reviewer",
    "ai_scan_plan_builder",
    "chat_task_dispatch_reviewer",
    "chatbot_flow_reviewer",
    "context_injection_safety_reviewer",
    "conversation_flow_designer",
    "infrastructure_cost_optimizer",
    "coverage_gap_analyzer",
    "devops_infrastructure_reviewer",
    "python_implementation_planner",
    "security_audit_planner",
    "security_test_plan_builder",
    "shell_command_execution_reviewer",
    "prompt_injection_scan_planner",
    "long_term_memory_policy_reviewer",
    "memory_writeback_reviewer",
    "multi_stage_reasoning_planner",
    "task_routing_policy_reviewer",
    "custom_agent_spec_builder",
    "skill_search_relevance_checker",
    "skill_gap_prioritizer",
    "defensive_osint_brief_builder",
    "source_synthesis_reviewer",
    "synthesis_quality_reviewer",
    "sec_filing_analysis_brief_builder",
    "legal_review_checklist_builder",
    "contract_draft_reviewer",
    "fundraising_readiness_reviewer",
    "investor_update_writer",
    "valuation_methodology_reviewer",
    "tax_calculation_reviewer",
    "payment_tracking_reconciler",
    "payment_validation_reviewer",
    "invoice_workflow_checker",
    "pnl_statement_reviewer",
    "profit_loss_draft_builder",
    "profit_loss_projection_reviewer",
    "daily_profit_alert_reviewer",
)

BATCH8_SKILL_IDS: tuple[str, ...] = (
    "email_ab_test_analyzer",
    "growth_ab_test_plan_reviewer",
    "accessibility_audit_checker",
    "trading_alert_format_reviewer",
    "customer_audit_trail_reviewer",
    "brand_positioning_reviewer",
    "marketing_budget_allocation_reviewer",
    "campaign_idea_brief_builder",
    "campaign_schedule_planner",
    "candidate_outreach_message_reviewer",
    "color_palette_system_reviewer",
    "comment_automation_safety_reviewer",
    "compensation_benchmark_brief_builder",
    "competitive_brand_analysis_reviewer",
    "component_spec_writer",
    "content_curation_planner",
    "social_content_generation_reviewer",
    "conversion_optimization_planner",
    "conversion_tracking_checker",
    "operating_cost_tracking_reviewer",
    "crypto_community_growth_planner",
    "dark_mode_accessibility_reviewer",
    "data_analysis_plan_reviewer",
    "email_deliverability_optimization_checker",
    "developer_handoff_package_reviewer",
    "dns_verification_checklist_builder",
    "document_generation_reviewer",
    "drip_sequence_planner",
    "earnings_quality_reviewer",
    "email_composition_reviewer",
    "email_sequence_planner",
    "engagement_tracking_reporter",
    "follow_up_automation_planner",
    "follow_up_message_writer",
    "follow_up_sequence_reviewer",
    "image_prompt_brief_builder",
    "image_prompt_safety_reviewer",
    "improvement_proposal_prioritizer",
    "interview_schedule_planner",
    "keyword_search_plan_builder",
)


PRODUCTION_FIELDS: tuple[str, ...] = (
    "subcategory",
    "version",
    "maturity_level",
    "what_it_does",
    "when_to_use",
    "when_not_to_use",
    "required_inputs",
    "optional_inputs",
    "execution_mode",
    "model_requirements",
    "context_requirements",
    "memory_usage",
    "tools_allowed",
    "tools_forbidden",
    "safety_level",
    "requires_human_approval",
    "risk_notes",
    "developer_prompt",
    "user_prompt_template",
    "internal_task_template",
    "examples",
    "quality_checklist",
    "success_criteria",
    "failure_modes",
    "fallback_strategy",
    "audit_events",
    "ui_metadata",
    "test_cases",
    "documentation_status",
)


def _missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def load_library(path: Path | None = None) -> dict[str, Any]:
    """Load the canonical skills library."""
    library_path = path or Path(__file__).resolve().parents[1] / "config" / "skills_library.json"
    return json.loads(library_path.read_text(encoding="utf-8"))


def _validate_skill_batch(
    batch_ids: tuple[str, ...],
    path: Path | None,
    expected_batch: str,
) -> dict[str, Any]:
    library = load_library(path)
    skills = library.get("skills", [])
    ids = [skill.get("id") for skill in skills]
    by_id = {skill.get("id"): skill for skill in skills}
    duplicate_ids = sorted({skill_id for skill_id in ids if ids.count(skill_id) > 1})

    missing_ids = [skill_id for skill_id in batch_ids if skill_id not in by_id]
    incomplete: dict[str, list[str]] = {}
    unwired: list[str] = []
    missing_aliases: list[str] = []
    wrong_batch: list[str] = []

    for skill_id in batch_ids:
        skill = by_id.get(skill_id)
        if not skill:
            continue
        missing_fields = [field for field in PRODUCTION_FIELDS if _missing_value(skill.get(field))]
        if missing_fields:
            incomplete[skill_id] = missing_fields
        ui = skill.get("ui_metadata") if isinstance(skill.get("ui_metadata"), dict) else {}
        if ui.get("wired") is not True:
            unwired.append(skill_id)
        if ui.get("batch") != expected_batch:
            wrong_batch.append(skill_id)
        if not skill.get("aliases"):
            missing_aliases.append(skill_id)

    meta_total = library.get("_meta", {}).get("total_skills")
    count_matches = meta_total == len(skills)
    ok = not (duplicate_ids or missing_ids or incomplete or unwired or missing_aliases or wrong_batch) and count_matches
    return {
        "ok": ok,
        "total": len(skills),
        "meta_total": meta_total,
        "count_matches": count_matches,
        "batch_size": len(batch_ids),
        "expected_batch": expected_batch,
        "duplicate_ids": duplicate_ids,
        "missing_ids": missing_ids,
        "incomplete": incomplete,
        "unwired": unwired,
        "missing_aliases": missing_aliases,
        "wrong_batch": wrong_batch,
    }


def validate_batch1_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the first 40 skills."""
    return _validate_skill_batch(BATCH1_SKILL_IDS, path, "batch_1")


def validate_batch2_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the second 40 skills."""
    return _validate_skill_batch(BATCH2_SKILL_IDS, path, "batch_2")


def validate_batch3_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the third 40 skills."""
    return _validate_skill_batch(BATCH3_SKILL_IDS, path, "batch_3")


def validate_batch4_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the fourth 40 skills."""
    return _validate_skill_batch(BATCH4_SKILL_IDS, path, "batch_4")


def validate_batch5_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the fifth 40 skills."""
    return _validate_skill_batch(BATCH5_SKILL_IDS, path, "batch_5")


def validate_batch6_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the sixth 40 skills."""
    return _validate_skill_batch(BATCH6_SKILL_IDS, path, "batch_6")


def validate_batch7_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the seventh 40 skills."""
    return _validate_skill_batch(BATCH7_SKILL_IDS, path, "batch_7")


def validate_batch8_library(path: Path | None = None) -> dict[str, Any]:
    """Return a structured readiness report for the eighth 40 skills."""
    return _validate_skill_batch(BATCH8_SKILL_IDS, path, "batch_8")

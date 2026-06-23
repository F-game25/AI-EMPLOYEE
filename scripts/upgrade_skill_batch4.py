#!/usr/bin/env python3
"""Upgrade the fourth 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "api_integration", "id": "api_integration_contract_tester", "name": "API Integration Contract Tester", "subcategory": "api-integration", "triggers": ["test api integration contract", "api integration check", "contract test integration"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "medium"},
    {"replace": "shopify_webhook", "id": "shopify_webhook_auditor", "name": "Shopify Webhook Auditor", "subcategory": "commerce-integration", "triggers": ["audit shopify webhook", "shopify webhook health", "webhook payload check"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "medium"},
    {"replace": "shopify_inventory_update", "id": "shopify_inventory_sync_checker", "name": "Shopify Inventory Sync Checker", "subcategory": "commerce-integration", "triggers": ["check shopify inventory sync", "inventory sync health", "shopify stock update"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "shopify_product_publish", "id": "shopify_publish_approval_planner", "name": "Shopify Publish Approval Planner", "subcategory": "commerce-approval", "triggers": ["plan shopify publish approval", "shopify product publish", "publish product review"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "stripe_data_pull", "id": "stripe_data_ingestion_checker", "name": "Stripe Data Ingestion Checker", "subcategory": "finance-integration", "triggers": ["check stripe data ingestion", "stripe data pull", "payment data import"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "quickbooks_sync", "id": "quickbooks_sync_reconciler", "name": "QuickBooks Sync Reconciler", "subcategory": "finance-integration", "triggers": ["reconcile quickbooks sync", "quickbooks data mismatch", "accounting sync check"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "mailchimp_integration", "id": "email_platform_integration_checker", "name": "Email Platform Integration Checker", "subcategory": "email-integration", "triggers": ["check email platform integration", "mailchimp integration", "email sync health"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "medium"},
    {"replace": "twilio_integration", "id": "twilio_integration_checker", "name": "Twilio Integration Checker", "subcategory": "communications-integration", "triggers": ["check twilio integration", "sms integration health", "twilio webhook"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "discord_integration", "id": "discord_integration_checker", "name": "Discord Integration Checker", "subcategory": "communications-integration", "triggers": ["check discord integration", "discord bot health", "discord webhook"], "tools": ["read_file", "http_request", "llm_infer"], "safety": "medium"},
    {"replace": "discord_whatsapp_notifications", "id": "cross_channel_notification_planner", "name": "Cross-Channel Notification Planner", "subcategory": "notification-ops", "triggers": ["plan cross channel notifications", "discord whatsapp notification", "notification routing plan"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "data_extraction", "id": "data_extraction_planner", "name": "Data Extraction Planner", "subcategory": "data-pipeline", "triggers": ["plan data extraction", "extract structured data", "data extraction workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "data_export", "id": "data_export_validator", "name": "Data Export Validator", "subcategory": "data-pipeline", "triggers": ["validate data export", "export data check", "data export quality"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "csv_generation", "id": "csv_output_validator", "name": "CSV Output Validator", "subcategory": "data-quality", "triggers": ["validate csv output", "csv format check", "csv generation quality"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "batch_processing", "id": "batch_job_planner", "name": "Batch Job Planner", "subcategory": "job-automation", "triggers": ["plan batch job", "batch processing plan", "batch workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "cron_management", "id": "cron_schedule_auditor", "name": "Cron Schedule Auditor", "subcategory": "job-automation", "triggers": ["audit cron schedule", "cron overlap check", "scheduled job review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "backup_management", "id": "backup_readiness_checker", "name": "Backup Readiness Checker", "subcategory": "resilience", "triggers": ["check backup readiness", "backup coverage", "restore readiness"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "archive_creation", "id": "archive_retention_planner", "name": "Archive Retention Planner", "subcategory": "resilience", "triggers": ["plan archive retention", "archive policy", "retention workflow"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "deployment_tracking", "id": "deployment_state_tracker", "name": "Deployment State Tracker", "subcategory": "release-ops", "triggers": ["track deployment state", "deployment status", "release progress"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "rollback_management", "id": "rollback_plan_reviewer", "name": "Rollback Plan Reviewer", "subcategory": "release-ops", "triggers": ["review rollback plan", "rollback readiness", "release rollback"], "tools": ["read_file", "llm_infer"], "safety": "high", "approval": True},
    {"replace": "patch_management", "id": "patch_rollout_planner", "name": "Patch Rollout Planner", "subcategory": "release-ops", "triggers": ["plan patch rollout", "patch management", "hotfix rollout"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "versioning", "id": "release_versioning_checker", "name": "Release Versioning Checker", "subcategory": "release-ops", "triggers": ["check release versioning", "version bump", "semantic version review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "changelog_generation", "id": "changelog_writer", "name": "Changelog Writer", "subcategory": "release-ops", "triggers": ["write changelog", "release notes", "changelog generation"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "diagnostic_reporting", "id": "diagnostic_report_builder", "name": "Diagnostic Report Builder", "subcategory": "observability", "triggers": ["build diagnostic report", "diagnostic summary", "system diagnostic report"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "anomaly_alerting", "id": "anomaly_alert_rule_planner", "name": "Anomaly Alert Rule Planner", "subcategory": "observability", "triggers": ["plan anomaly alert rule", "anomaly alerting", "alert threshold plan"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "system_health_reporting", "id": "system_status_reporter", "name": "System Status Reporter", "subcategory": "observability", "triggers": ["write system status", "system health report", "status report"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "agent_coordination", "id": "agent_coordination_planner", "name": "Agent Coordination Planner", "subcategory": "agent-orchestration", "triggers": ["plan agent coordination", "coordinate agents", "multi agent handoff"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "agent_selection", "id": "agent_selection_evaluator", "name": "Agent Selection Evaluator", "subcategory": "agent-orchestration", "triggers": ["evaluate agent selection", "choose agent", "agent fit"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "agent_dispatch", "id": "agent_dispatch_auditor", "name": "Agent Dispatch Auditor", "subcategory": "agent-orchestration", "triggers": ["audit agent dispatch", "agent dispatch route", "dispatch quality"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "agent_composition", "id": "agent_composition_designer", "name": "Agent Composition Designer", "subcategory": "agent-orchestration", "triggers": ["design agent composition", "compose agent team", "agent capability mix"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "bot_lifecycle", "id": "bot_lifecycle_manager", "name": "Bot Lifecycle Manager", "subcategory": "agent-orchestration", "triggers": ["manage bot lifecycle", "bot lifecycle", "agent lifecycle"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "state_aggregation", "id": "state_snapshot_aggregator", "name": "State Snapshot Aggregator", "subcategory": "state-management", "triggers": ["aggregate state snapshot", "system state snapshot", "state aggregation"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "result_synthesis", "id": "multi_agent_result_synthesizer", "name": "Multi-Agent Result Synthesizer", "subcategory": "agent-orchestration", "triggers": ["synthesize multi agent results", "merge agent findings", "result synthesis"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "multi_agent_coordination", "id": "multi_agent_coordination_reviewer", "name": "Multi-Agent Coordination Reviewer", "subcategory": "agent-orchestration", "triggers": ["review multi agent coordination", "multi agent coordination", "agent collaboration review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "multi_agent_synthesis", "id": "multi_agent_synthesis_reviewer", "name": "Multi-Agent Synthesis Reviewer", "subcategory": "agent-orchestration", "triggers": ["review multi agent synthesis", "multi agent synthesis", "agent synthesis quality"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "provider_fallback", "id": "provider_fallback_planner", "name": "Provider Fallback Planner", "subcategory": "runtime-resilience", "triggers": ["plan provider fallback", "fallback provider", "model provider outage"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "session_persistence", "id": "session_persistence_checker", "name": "Session Persistence Checker", "subcategory": "runtime-resilience", "triggers": ["check session persistence", "session recovery", "state persistence"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "vault_index_management", "id": "vault_index_health_checker", "name": "Vault Index Health Checker", "subcategory": "knowledge-runtime", "triggers": ["check vault index health", "vault index", "knowledge index health"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "vault_knowledge_retrieval", "id": "vault_retrieval_quality_checker", "name": "Vault Retrieval Quality Checker", "subcategory": "knowledge-runtime", "triggers": ["check vault retrieval quality", "knowledge retrieval quality", "retrieval audit"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "trigger_configuration", "id": "trigger_rule_auditor", "name": "Trigger Rule Auditor", "subcategory": "automation-governance", "triggers": ["audit trigger rules", "trigger configuration", "automation trigger review"], "tools": ["read_file", "llm_infer"], "safety": "medium"},
    {"replace": "template_scoring", "id": "template_quality_scorer", "name": "Template Quality Scorer", "subcategory": "automation-quality", "triggers": ["score template quality", "template scoring", "template quality review"], "tools": ["read_file", "llm_infer"], "safety": "low"},
)


def _category(subcategory: str) -> str:
    if "integration" in subcategory or subcategory in {"notification-ops"}:
        return "Integration & Runtime"
    if subcategory.startswith("data"):
        return "Data Analysis"
    if subcategory in {"job-automation", "resilience", "automation-governance", "automation-quality"}:
        return "Automation & Productivity"
    if subcategory in {"release-ops", "observability", "runtime-resilience", "knowledge-runtime"}:
        return "Development & Technical"
    if subcategory in {"agent-orchestration", "state-management"}:
        return "Project Management"
    if subcategory == "commerce-approval":
        return "E-commerce & Product"
    return "Automation & Productivity"


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    approval_note = "Requires human approval before syncing data, publishing products, sending notifications, rolling back releases, changing credentials, or modifying external systems."

    required_inputs = ["task_goal", "system_context", "constraints"]
    optional_inputs = ["source_files", "service_names", "sample_payloads", "logs", "approval_context", "previous_results"]
    when_not = [
        "Do not use when the request is unrelated to integrations, data pipelines, release operations, observability, runtime resilience, or agent orchestration.",
        "Do not invent service state, payloads, logs, credentials, sync status, or external system outcomes.",
    ]
    if approval:
        when_not.append("Do not perform side effects until a human explicitly approves the prepared plan, check, or operation.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge. "
        "Operate as a senior reliability engineer: ground work in supplied system context, "
        "separate facts from assumptions, produce reviewable checks or plans, and never claim external actions happened unless verified. "
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
        "maturity_level": "production_batch_4",
        "description": f"{spec['name']}: production-ready reliability skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Turns {spec['subcategory'].replace('-', ' ')} requests into grounded checks, plans, audits, or reviewable artifacts with explicit approval and audit behavior.",
        "when_to_use": spec["triggers"],
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_integrations_reliability_or_multi_step_workflows",
            "escalate_when": ["low_confidence", "external_service_risk", "data_integrity_risk", "rollback_or_publish_boundary"],
        },
        "context_requirements": [
            "Relevant files, service contracts, payload samples, logs, runbooks, or system state must be supplied or discoverable.",
            "Approval boundaries and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"deployment_state_tracker", "system_status_reporter", "state_snapshot_aggregator", "vault_index_health_checker"},
            "notes": "Use memory for prior integration incidents, release decisions, runbook lessons, and post-result summaries when useful.",
        },
        "tools_allowed": list(spec["tools"]),
        "tools_forbidden": ["unapproved_external_delivery", "unapproved_account_change", "payment_execution", "secret_exfiltration", "destructive_rollback", "unapproved_publish"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": approval_note if approval else "Planning, audit, or review skill; still surface uncertainty, data gaps, and external-service assumptions.",
        "system_prompt": system_prompt,
        "developer_prompt": (
            "Respect AscendForge approval gates, auditability, sandboxing, and tenant boundaries. "
            "For integrations, syncs, releases, notifications, data exports, and runtime changes, prepare a reviewable artifact first. "
            "Include validation checks, blocked actions, rollback considerations, and the smallest safe next step."
        ),
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with system context {{system_context}} and constraints {{constraints}}.",
        "internal_task_template": {
            "skill_id": spec["id"],
            "task_goal": "{{task_goal}}",
            "system_context": "{{system_context}}",
            "constraints": "{{constraints}}",
            "approval_required": approval,
        },
        "examples": [
            f"Use {spec['name']} to {spec['triggers'][0]} for an AscendForge reliability workflow.",
            f"Run {spec['name']} and return findings, assumptions, risks, approval needs, and validation steps.",
        ],
        "quality_checklist": [
            "Uses real supplied or discoverable system context.",
            "States assumptions, missing context, and blocked external actions.",
            "Separates findings or artifact, rationale, validation, risks, and next steps.",
            "Does not claim syncs, publishes, notifications, rollbacks, or external changes unless actually executed through approval.",
            "Applies approval gates for data integrity, external integrations, release operations, notifications, and destructive actions.",
        ],
        "success_criteria": [
            "Output is specific enough for a human or agent to review and execute.",
            "External service, data, release, runtime, or orchestration risk is explicit.",
            "Verification or acceptance checks are included.",
        ],
        "failure_modes": ["missing_context", "ambiguous_goal", "tool_unavailable", "approval_required", "data_unverified", "external_state_unknown"],
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
            "batch": "batch_4",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "bronze",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 121,
        },
        "test_cases": [
            {"name": f"selects_{spec['id']}", "input": spec["triggers"][0], "expected": {"selected_skill_id": spec["id"], "status": "selected"}},
            {"name": f"approval_or_gap_behavior_{spec['id']}", "input": "missing approval or system context", "expected": {"status": "blocked_or_gap_reported"}},
        ],
        "documentation_status": "documented_batch_4",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return findings, assumptions, validation, risks, approval needs, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-4", "production-skill", "reliability"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "reliability-agent", "integration-agent"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing system context rather than inventing payloads, logs, service state, or external outcomes.",
        },
        "output_format": {
            "sections": ["findings", "assumptions", "validation", "risks", "approval_needs", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what is checked, planned, blocked, and what remains unverified.",
        },
        "quality_standards": [
            "Grounded in real integration, release, data, runtime, or orchestration context.",
            "Approval and audit boundaries respected.",
            "No fake integrations, syncs, notifications, rollbacks, publishes, or external state claims.",
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
            "Never bypass approval for external integration, data sync, release, notification, publish, or rollback actions.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required system context and report gaps.",
            "Prepare the check, audit, plan, or review using allowed tools only.",
            "Apply approval and audit criteria before any consequential next action.",
            "Return findings, validation, risk notes, approval needs, and next steps.",
        ],
        "source": "batch4_production_upgrade",
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
    data["_meta"]["batch4_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

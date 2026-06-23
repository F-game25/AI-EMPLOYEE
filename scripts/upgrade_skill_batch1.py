#!/usr/bin/env python3
"""Upgrade the first 40 production skills in-place without changing count."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "runtime" / "config" / "skills_library.json"


REPLACEMENTS: tuple[dict[str, Any], ...] = (
    {"replace": "code_generation", "id": "codebase_reader", "name": "Codebase Reader", "subcategory": "code-intelligence", "triggers": ["read codebase", "inspect repository", "understand files"], "tools": ["read_file", "grep_callers"], "safety": "low"},
    {"replace": "system_architecture", "id": "architecture_mapper", "name": "Architecture Mapper", "subcategory": "architecture", "triggers": ["map architecture", "system design", "service boundaries"], "tools": ["read_file", "grep_callers"], "safety": "low"},
    {"replace": "debugging", "id": "bug_finder", "name": "Bug Finder", "subcategory": "debugging", "triggers": ["find bug", "broken behavior", "defect"], "tools": ["read_file", "grep_callers", "run_tests"], "safety": "low"},
    {"replace": "bug_reporting", "id": "error_trace_analyzer", "name": "Error Trace Analyzer", "subcategory": "debugging", "triggers": ["stack trace", "exception", "traceback"], "tools": ["read_file", "grep_callers"], "safety": "low"},
    {"replace": "refactoring", "id": "refactor_planner", "name": "Refactor Planner", "subcategory": "maintenance", "triggers": ["refactor plan", "simplify module", "technical debt"], "tools": ["read_file", "grep_callers"], "safety": "medium"},
    {"replace": "security_review", "id": "secure_code_reviewer", "name": "Secure Code Reviewer", "subcategory": "security-review", "triggers": ["secure review", "auth bypass", "injection"], "tools": ["read_file", "grep_patterns"], "safety": "medium"},
    {"replace": "test_automation_strategy", "id": "test_generator", "name": "Test Generator", "subcategory": "testing", "triggers": ["generate tests", "test coverage", "unit test"], "tools": ["read_file", "write_file", "run_tests"], "safety": "medium", "approval": True},
    {"replace": "accessibility_testing", "id": "ui_ux_auditor", "name": "UI/UX Auditor", "subcategory": "ui-quality", "triggers": ["audit ui", "ux review", "dashboard polish"], "tools": ["read_file", "browser_snapshot"], "safety": "low"},
    {"replace": "api_testing", "id": "api_route_inspector", "name": "API Route Inspector", "subcategory": "api", "triggers": ["inspect api", "route audit", "endpoint"], "tools": ["read_file", "grep_callers"], "safety": "low"},
    {"replace": "database_design", "id": "database_schema_analyzer", "name": "Database Schema Analyzer", "subcategory": "database", "triggers": ["schema", "database model", "migration"], "tools": ["read_file", "grep_callers"], "safety": "medium"},
    {"replace": "task_planning", "id": "agent_task_planner", "name": "Agent Task Planner", "subcategory": "agent-orchestration", "triggers": ["agent plan", "task graph", "work plan"], "tools": ["llm_infer", "get_memory"], "safety": "low"},
    {"replace": "task_decomposition", "id": "agent_task_decomposer", "name": "Agent Task Decomposer", "subcategory": "agent-orchestration", "triggers": ["decompose task", "break down goal", "subtasks"], "tools": ["llm_infer", "get_memory"], "safety": "low"},
    {"replace": "file_ops", "id": "local_file_reader", "name": "Local File Reader", "subcategory": "filesystem", "triggers": ["read local file", "inspect file", "open file"], "tools": ["read_file"], "safety": "low"},
    {"replace": "output_management", "id": "local_file_writer", "name": "Local File Writer", "subcategory": "filesystem", "triggers": ["write local file", "save file", "create file"], "tools": ["write_file", "create_file"], "safety": "high", "approval": True},
    {"replace": "web_scraping", "id": "browser_research_skill", "name": "Browser Research Skill", "subcategory": "browser-research", "triggers": ["browser research", "web research", "fetch sources"], "tools": ["web_search", "browser_fetch", "fetch_page"], "safety": "medium"},
    {"replace": "source_attribution", "id": "source_credibility_checker", "name": "Source Credibility Checker", "subcategory": "research-quality", "triggers": ["credible source", "source quality", "verify citation"], "tools": ["web_search", "fetch_page"], "safety": "low"},
    {"replace": "documentation", "id": "documentation_writer", "name": "Documentation Writer", "subcategory": "documentation", "triggers": ["write docs", "document feature", "readme"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "workflow_planning", "id": "implementation_plan_writer", "name": "Implementation Plan Writer", "subcategory": "planning", "triggers": ["implementation plan", "build plan", "execution plan"], "tools": ["read_file", "llm_infer"], "safety": "low"},
    {"replace": "prompt_optimization", "id": "prompt_optimizer", "name": "Prompt Optimizer", "subcategory": "context-engineering", "triggers": ["improve prompt", "prompt quality", "system prompt"], "tools": ["llm_infer"], "safety": "low"},
    {"replace": "context_checkpointing", "id": "context_compressor", "name": "Context Compressor", "subcategory": "context-engineering", "triggers": ["compress context", "summarize session", "reduce tokens"], "tools": ["llm_infer", "get_memory"], "safety": "low"},
    {"replace": "memory_retrieval", "id": "memory_linker", "name": "Memory Linker", "subcategory": "memory", "triggers": ["link memory", "retrieve memory", "connect context"], "tools": ["get_memory", "embed_text"], "safety": "low"},
    {"replace": "model_routing", "id": "model_router_evaluator", "name": "Model Router Evaluator", "subcategory": "model-routing", "triggers": ["model routing", "choose model", "route evaluator"], "tools": ["llm_infer"], "safety": "low"},
    {"replace": "structured_output", "id": "llm_output_judge", "name": "LLM Output Judge", "subcategory": "evaluation", "triggers": ["judge output", "evaluate answer", "quality gate"], "tools": ["llm_infer"], "safety": "low"},
    {"replace": "performance_testing", "id": "failure_forensics_analyzer", "name": "Failure Forensics Analyzer", "subcategory": "reliability", "triggers": ["failure analysis", "forensics", "root cause"], "tools": ["read_file", "grep_patterns"], "safety": "low"},
    {"replace": "readiness_certification", "id": "regression_detector", "name": "Regression Detector", "subcategory": "testing", "triggers": ["regression", "changed behavior", "detect breakage"], "tools": ["run_tests", "read_file"], "safety": "medium"},
    {"replace": "test_plan_creation", "id": "sandbox_test_runner", "name": "Sandbox Test Runner", "subcategory": "testing", "triggers": ["sandbox test", "run tests safely", "verification"], "tools": ["run_tests", "node_check"], "safety": "medium", "approval": True},
    {"replace": "security_posture_analysis", "id": "security_threat_modeler", "name": "Security Threat Modeler", "subcategory": "security", "triggers": ["threat model", "risk model", "attack surface"], "tools": ["read_file", "grep_patterns"], "safety": "medium"},
    {"replace": "dependency_analysis", "id": "dependency_vulnerability_checker", "name": "Dependency Vulnerability Checker", "subcategory": "security", "triggers": ["dependency vulnerability", "package risk", "supply chain"], "tools": ["read_file", "grep_patterns"], "safety": "medium"},
    {"replace": "command_handling", "id": "command_safety_classifier", "name": "Command Safety Classifier", "subcategory": "command-safety", "triggers": ["classify command", "command safety", "shell risk"], "tools": ["llm_infer"], "safety": "high", "approval": True},
    {"replace": "approval_workflows", "id": "human_approval_gate_planner", "name": "Human Approval Gate Planner", "subcategory": "approval", "triggers": ["approval gate", "human review", "hitl"], "tools": ["llm_infer"], "safety": "high", "approval": True},
    {"replace": "code_exec", "id": "remote_compute_planner", "name": "Remote Compute Planner", "subcategory": "compute", "triggers": ["remote compute", "external compute", "gpu plan"], "tools": ["llm_infer"], "safety": "high", "approval": True},
    {"replace": "usage_analytics", "id": "resource_usage_optimizer", "name": "Resource Usage Optimizer", "subcategory": "performance", "triggers": ["resource usage", "optimize memory", "reduce cost"], "tools": ["system_hardware", "llm_infer"], "safety": "low"},
    {"replace": "system_health_monitoring", "id": "system_startup_diagnostics", "name": "System Startup Diagnostics", "subcategory": "health", "triggers": ["startup diagnostics", "boot check", "system start"], "tools": ["system_hardware", "system_cwd"], "safety": "low"},
    {"replace": "frontend_development", "id": "frontend_build_checker", "name": "Frontend Build Checker", "subcategory": "frontend", "triggers": ["frontend build", "vite build", "react build"], "tools": ["run_build", "node_check"], "safety": "medium"},
    {"replace": "backend_architecture", "id": "backend_health_checker", "name": "Backend Health Checker", "subcategory": "backend", "triggers": ["backend health", "node server", "api health"], "tools": ["http_request", "node_check"], "safety": "low"},
    {"replace": "service_validation", "id": "python_service_health_checker", "name": "Python Service Health Checker", "subcategory": "python", "triggers": ["python backend health", "fastapi health", "uvicorn"], "tools": ["http_request", "system_cwd"], "safety": "low"},
    {"replace": "model_budget_planning", "id": "ollama_model_checker", "name": "Ollama Model Checker", "subcategory": "model-runtime", "triggers": ["ollama model", "local model", "model installed"], "tools": ["http_request", "llm_infer"], "safety": "low"},
    {"replace": "skill_library", "id": "skill_registry_validator", "name": "Skill Registry Validator", "subcategory": "skill-system", "triggers": ["skill registry", "validate skills", "skill schema"], "tools": ["read_file"], "safety": "low"},
    {"replace": "skill_routing", "id": "dashboard_skill_sync_checker", "name": "Dashboard Skill Sync Checker", "subcategory": "dashboard", "triggers": ["dashboard skill sync", "ui skills", "skill visibility"], "tools": ["read_file", "http_request"], "safety": "low"},
    {"replace": "task_resumption", "id": "end_to_end_task_executor", "name": "End-to-End Task Executor", "subcategory": "execution", "triggers": ["execute task end to end", "run workflow", "complete task"], "tools": ["llm_infer", "get_memory"], "safety": "high", "approval": True},
)


def _sentence_list(name: str, values: list[str]) -> list[str]:
    return [f"{name}: {value}." for value in values]


def build_skill(old: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    old_id = str(old.get("id") or spec["replace"])
    aliases = [old_id, old_id.replace("_", "-"), *old.get("aliases", [])]
    aliases = sorted({str(alias) for alias in aliases if alias and str(alias) != spec["id"]})
    tools = list(spec["tools"])
    approval = bool(spec.get("approval"))
    safety = str(spec.get("safety", "low"))
    risk_level = "dangerous" if safety == "high" else "caution" if safety == "medium" else "safe"
    category = "Development & Technical"
    if spec["subcategory"] in {"browser-research", "research-quality"}:
        category = "Research & Analysis"
    elif spec["subcategory"] in {"agent-orchestration", "planning", "execution"}:
        category = "Project Management"
    elif spec["subcategory"] in {"memory", "context-engineering", "model-routing", "evaluation"}:
        category = "Automation & Productivity"

    required_inputs = ["task_goal", "context", "constraints"]
    optional_inputs = ["files", "examples", "previous_errors", "deadline", "approval_context"]
    when_to_use = spec["triggers"]
    when_not = [
        "Do not use when the user is asking for unrelated business/content work.",
        "Do not execute side effects directly when the skill is planning-only or approval-gated.",
    ]
    if approval:
        when_not.append("Do not proceed with external, write, shell, spend, or account-changing actions before human approval.")

    system_prompt = (
        f"You are the {spec['name']} production skill inside AscendForge / Nexus OS. "
        "Work as a senior engineer: inspect real context, separate facts from assumptions, "
        "return decision-ready output, and never invent integrations or success. "
        f"Primary triggers: {', '.join(spec['triggers'])}. "
        f"Safety level: {safety}. "
        + ("Require human approval before consequential action. " if approval else "")
        + "If required context is missing, return a gap report and fallback path."
    )
    developer_prompt = (
        "Use existing repository architecture and current skill contracts. "
        "Prefer read-only inspection unless the task explicitly enters an approved execution path. "
        "Include validation notes, failure modes, and next steps."
    )

    skill = {
        **old,
        "id": spec["id"],
        "name": spec["name"],
        "category": category,
        "subcategory": spec["subcategory"],
        "version": "1.0.0",
        "maturity_level": "production_batch_1",
        "description": f"{spec['name']}: production-ready system skill for {spec['subcategory'].replace('-', ' ')} workflows.",
        "what_it_does": f"Handles {spec['subcategory'].replace('-', ' ')} tasks with explicit inputs, outputs, safety gates, and validation.",
        "when_to_use": when_to_use,
        "when_not_to_use": when_not,
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "execution_mode": "approval_gated_tool_plan" if approval else "tool_guided_llm",
        "model_requirements": {
            "minimum": "local_reasoning_model_or_cloud_fallback",
            "preferred": "strong_reasoning_for_code_security_or_multi_step_tasks",
            "escalate_when": ["low_confidence", "large_codebase", "security_or_money_risk", "external_side_effect"],
        },
        "context_requirements": [
            "Relevant files, routes, schemas, logs, or system state must be supplied or discoverable.",
            "Constraints and desired output format must be explicit.",
        ],
        "memory_usage": {
            "read": True,
            "write": spec["id"] in {"memory_linker", "context_compressor", "end_to_end_task_executor"},
            "notes": "Use memory for prior decisions, project conventions, and post-result summaries when useful.",
        },
        "tools_allowed": tools,
        "tools_forbidden": ["rm_rf", "git_push_force", "database_drop", "secret_exfiltration", "unapproved_external_delivery"],
        "safety_level": safety,
        "requires_human_approval": approval,
        "risk_level": risk_level,
        "approval_policy": "human_approval_required_for_side_effects" if approval else "read_or_plan_without_side_effects",
        "risk_notes": (
            "Approval is required before writes, shell execution, browser actions with side effects, remote compute, spend, publishing, or external delivery."
            if approval else
            "Read-only or planning-oriented; still report uncertainty and avoid unsafe recommendations."
        ),
        "system_prompt": system_prompt,
        "developer_prompt": developer_prompt,
        "user_prompt_template": f"Use {spec['name']} for {{task_goal}} with context {{context}} and constraints {{constraints}}.",
        "internal_task_template": {
            "skill_id": spec["id"],
            "task_goal": "{{task_goal}}",
            "context": "{{context}}",
            "constraints": "{{constraints}}",
            "approval_required": approval,
        },
        "examples": [
            f"Use {spec['name']} to {spec['triggers'][0]} for this repository.",
            f"Run {spec['name']} and return findings, risks, and verification steps.",
        ],
        "quality_checklist": [
            "Uses real supplied or discoverable context.",
            "States assumptions and missing context.",
            "Separates result, rationale, validation, risks, and next steps.",
            "Does not claim execution when only planning occurred.",
            "Applies approval gates for consequential actions.",
        ],
        "success_criteria": [
            "Output is specific enough for an agent or engineer to act on.",
            "Relevant safety and failure behavior is explicit.",
            "Verification or acceptance checks are included.",
        ],
        "failure_modes": [
            "missing_context",
            "ambiguous_goal",
            "tool_unavailable",
            "approval_required",
            "validation_failed",
        ],
        "fallback_strategy": "Return a partial result with gaps, blocked actions, and the exact context or approval needed to continue.",
        "audit_events": [
            f"skill.{spec['id']}.selected",
            f"skill.{spec['id']}.completed",
            f"skill.{spec['id']}.blocked",
        ],
        "ui_metadata": {
            "visible": True,
            "wired": True,
            "dashboard_section": "skills",
            "batch": "batch_1",
            "status": "production_ready",
            "icon": "shield" if safety == "high" else "check-circle" if safety == "medium" else "sparkles",
            "accent": "bronze",
            "display_order": [item["id"] for item in REPLACEMENTS].index(spec["id"]) + 1,
        },
        "test_cases": [
            {
                "name": f"selects_{spec['id']}",
                "input": spec["triggers"][0],
                "expected": {"selected_skill_id": spec["id"], "status": "selected"},
            },
            {
                "name": f"blocks_or_reports_gaps_{spec['id']}",
                "input": "missing context",
                "expected": {"status": "blocked_or_gap_reported"},
            },
        ],
        "documentation_status": "documented_batch_1",
        "prompt_hint": f"Apply {spec['name']} to [goal]. Return result, rationale, validation, risks, and next steps.",
        "tags": sorted({*old.get("tags", []), *spec["id"].split("_"), spec["subcategory"], "batch-1", "production-skill"}),
        "aliases": aliases,
        "compatible_agents": sorted({*old.get("compatible_agents", []), "ascend-forge", "task-orchestrator", "engineering-assistant", "problem-solver"}),
        "input_format": {
            "required_fields": required_inputs,
            "optional_fields": optional_inputs,
            "input_contract": "Reject empty goals. Ask for or report missing context rather than inventing details.",
        },
        "output_format": {
            "sections": ["result", "rationale", "validation", "risks", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must show what was done or planned, what was verified, and what remains blocked.",
        },
        "quality_standards": [
            "Complete and unambiguous output.",
            "Grounded in real system context.",
            "Safety and approval gates respected.",
            f"{spec['name']} passes its production quality checklist.",
        ],
        "error_handling": {
            "retryable_errors": ["temporary_dependency_failure", "timeout", "transient_model_failure"],
            "non_retryable_errors": ["missing_context", "approval_required", "forbidden_policy_action", "validation_failure"],
            "fallback_strategy": "Return a gap report with the smallest safe next step.",
        },
        "best_practices": [
            "Inspect before recommending changes.",
            "Use existing project patterns.",
            "Keep outputs structured and verifiable.",
            "Log or request approval for policy-relevant work.",
        ],
        "execution_steps": [
            f"Classify whether {spec['name']} is the right skill for the goal.",
            "Collect required context and report gaps.",
            "Apply the skill workflow using allowed tools only.",
            "Check output against success criteria and failure modes.",
            "Return result, validation, risk notes, and next steps.",
        ],
        "source": "batch1_production_upgrade",
        "replaces_skill_id": old_id,
    }
    return skill


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
    data["_meta"]["batch1_production_upgrade"] = {
        "count": len(REPLACEMENTS),
        "mode": "canonical_replacements_preserve_total",
        "total_skills_preserved": len(skills),
    }
    LIBRARY.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Upgraded {len(REPLACEMENTS)} skills; total remains {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

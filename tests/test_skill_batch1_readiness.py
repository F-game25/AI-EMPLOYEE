from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


def test_batch1_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH1_SKILL_IDS, validate_batch1_library

    report = validate_batch1_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH1_SKILL_IDS) == 40


def test_batch2_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH2_SKILL_IDS, validate_batch2_library

    report = validate_batch2_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH2_SKILL_IDS) == 40


def test_batch3_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH3_SKILL_IDS, validate_batch3_library

    report = validate_batch3_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH3_SKILL_IDS) == 40


def test_batch4_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH4_SKILL_IDS, validate_batch4_library

    report = validate_batch4_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH4_SKILL_IDS) == 40


def test_batch5_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH5_SKILL_IDS, validate_batch5_library

    report = validate_batch5_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH5_SKILL_IDS) == 40


def test_batch6_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH6_SKILL_IDS, validate_batch6_library

    report = validate_batch6_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH6_SKILL_IDS) == 40


def test_batch7_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH7_SKILL_IDS, validate_batch7_library

    report = validate_batch7_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH7_SKILL_IDS) == 40


def test_batch8_library_is_ready_and_count_preserved():
    from skills.batch1_readiness import BATCH8_SKILL_IDS, validate_batch8_library

    report = validate_batch8_library()
    assert report["ok"], report
    assert report["batch_size"] == 40
    assert report["total"] == 571
    assert len(BATCH8_SKILL_IDS) == 40


def test_batch1_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("debugging")["id"] == "bug_finder"
    assert registry.skill("model_routing")["id"] == "model_router_evaluator"
    assert registry.skill("skill_library")["id"] == "skill_registry_validator"


def test_batch2_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("deal_matching")["id"] == "paid_task_evaluator"
    assert registry.skill("email_personalization")["id"] == "email_personalizer"
    assert registry.skill("audit_logging")["id"] == "audit_log_reviewer"


def test_batch3_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("seo_audit")["id"] == "seo_opportunity_auditor"
    assert registry.skill("invoice_generation")["id"] == "invoice_draft_reviewer"
    assert registry.skill("tool_policy_gating")["id"] == "tool_policy_review_planner"


def test_batch4_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("api_integration")["id"] == "api_integration_contract_tester"
    assert registry.skill("rollback_management")["id"] == "rollback_plan_reviewer"
    assert registry.skill("vault_knowledge_retrieval")["id"] == "vault_retrieval_quality_checker"


def test_batch5_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("customer_service")["id"] == "customer_service_workflow_planner"
    assert registry.skill("cold_email_writing")["id"] == "cold_email_draft_reviewer"
    assert registry.skill("fact_verification")["id"] == "fact_checking_workflow_runner"


def test_batch6_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("workflow_management")["id"] == "workflow_management_auditor"
    assert registry.skill("auto_reorder")["id"] == "auto_reorder_policy_reviewer"
    assert registry.skill("action_item_extraction")["id"] == "action_item_tracker"


def test_batch7_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("shell_exec")["id"] == "shell_command_execution_reviewer"
    assert registry.skill("legal_review")["id"] == "legal_review_checklist_builder"
    assert registry.skill("agent_memory")["id"] == "agent_memory_health_checker"


def test_batch8_replaced_ids_resolve_as_aliases():
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    assert registry.skill("accessibility_audit")["id"] == "accessibility_audit_checker"
    assert registry.skill("deliverability_optimization")["id"] == "email_deliverability_optimization_checker"
    assert registry.skill("comment_automation")["id"] == "comment_automation_safety_reviewer"


def test_skill_selector_uses_production_metadata():
    from forge.lifecycle.skill_selector import select_skills

    picks = select_skills("please map architecture and service boundaries", "architecture", max_skills=3)
    assert picks
    assert picks[0]["id"] == "architecture_mapper"

    picks = select_skills("check dashboard skill sync and visible skill metadata", "dashboard", max_skills=3)
    assert any(p["id"] == "dashboard_skill_sync_checker" for p in picks)

    picks = select_skills("evaluate this paid task and score the client opportunity", "money mode", max_skills=3)
    assert any(p["id"] == "paid_task_evaluator" for p in picks)

    picks = select_skills("check secrets exposure and credential leaks", "security", max_skills=3)
    assert any(p["id"] == "secrets_exposure_checker" for p in picks)

    picks = select_skills("audit seo opportunities and search visibility gaps", "growth", max_skills=3)
    assert any(p["id"] == "seo_opportunity_auditor" for p in picks)

    picks = select_skills("review invoice draft before sending payment request", "finance", max_skills=3)
    assert any(p["id"] == "invoice_draft_reviewer" for p in picks)

    picks = select_skills("test api integration contract and webhook payload handling", "integration", max_skills=3)
    assert any(p["id"] == "api_integration_contract_tester" for p in picks)

    picks = select_skills("review rollback plan and release rollback readiness", "release", max_skills=3)
    assert any(p["id"] == "rollback_plan_reviewer" for p in picks)

    picks = select_skills("review cold email draft for outreach risk", "sales", max_skills=3)
    assert any(p["id"] == "cold_email_draft_reviewer" for p in picks)

    picks = select_skills("run fact verification for these claims", "research", max_skills=3)
    assert any(p["id"] == "fact_checking_workflow_runner" for p in picks)

    picks = select_skills("audit workflow management and workflow health", "workflow", max_skills=3)
    assert any(p["id"] == "workflow_management_auditor" for p in picks)

    picks = select_skills("review auto reorder policy before changing inventory rules", "commerce", max_skills=3)
    assert any(p["id"] == "auto_reorder_policy_reviewer" for p in picks)

    picks = select_skills("review shell command execution risk before running this command", "security", max_skills=3)
    assert any(p["id"] == "shell_command_execution_reviewer" for p in picks)

    picks = select_skills("build legal review checklist for this contract", "legal", max_skills=3)
    assert any(p["id"] == "legal_review_checklist_builder" for p in picks)

    picks = select_skills("check accessibility audit and dark mode contrast issues", "ui", max_skills=3)
    assert any(p["id"] == "accessibility_audit_checker" for p in picks)

    picks = select_skills("check email deliverability optimization and DNS records", "email", max_skills=3)
    assert any(p["id"] == "email_deliverability_optimization_checker" for p in picks)


def test_dispatch_explicit_batch_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "check whether this shell command is safe",
            {"skill_id": "command_safety_classifier"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "command_safety_classifier"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch2_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "money-mode metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "write a client proposal for this paid task",
            {"skill_id": "proposal_writer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "proposal_writer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "medium"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch3_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "operations metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "review the invoice draft before it is sent",
            {"skill_id": "invoice_draft_reviewer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "invoice_draft_reviewer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch4_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "reliability metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "review rollback plan before release rollback",
            {"skill_id": "rollback_plan_reviewer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "rollback_plan_reviewer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch5_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "customer and outreach metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "review this cold email draft before outreach",
            {"skill_id": "cold_email_draft_reviewer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "cold_email_draft_reviewer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch6_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "commerce workflow metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "review auto reorder policy before changing stock rules",
            {"skill_id": "auto_reorder_policy_reviewer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "auto_reorder_policy_reviewer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]


def test_dispatch_explicit_batch7_skill_uses_metadata():
    from skills.catalog import ExecutableSkillCatalog

    engine = ModuleType("engine.api")
    captured = {}

    def fake_generate(prompt, system=None, context=None):
        captured["system"] = system
        return "governance metadata-aware output"

    engine.generate = fake_generate
    catalog = ExecutableSkillCatalog()

    with patch.dict(sys.modules, {"engine.api": engine}):
        out = catalog.dispatch_for_goal(
            "review shell command execution before running",
            {"skill_id": "shell_command_execution_reviewer"},
        )

    assert out["status"] == "ok"
    assert out["skill_id"] == "shell_command_execution_reviewer"
    assert out["requires_human_approval"] is True
    assert out["safety_level"] == "high"
    assert "Developer guidance" in captured["system"]
    assert "Human approval is required" in captured["system"]

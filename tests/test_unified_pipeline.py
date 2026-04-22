"""Tests for runtime/core/unified_pipeline.py

Covers all 10 pipeline phases:
  Phase 2  — retrieve_relevant_nodes
  Phase 2b — build_context
  Phase 3  — classify_decision
  Phase 5  — decompose_to_tasks
  Phase 6  — execute_tasks
  Phase 7  — format_response
  Phase 8  — update_graph
  Phase 9  — monitor_and_improve
  Phase 10 — validate_pipeline_integrity
  Phase 1  — process_user_input (integration)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_RUNTIME_DIR = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from core.unified_pipeline import (
    PipelineViolationError,
    _PipelineRun,
    _FALLBACK_PREFIX,
    build_context,
    classify_decision,
    decompose_to_tasks,
    execute_tasks,
    format_response,
    monitor_and_improve,
    process_user_input,
    retrieve_relevant_nodes,
    update_graph,
    validate_pipeline_integrity,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _run(
    input_text: str = "test input",
    *,
    llm_called: bool = True,
    tasks_executed: int = 1,
    response: str = "A real response",
    graph_data: dict | None = None,
) -> _PipelineRun:
    run = _PipelineRun(input_text, "user1", "power", "")
    run.graph_data = graph_data if graph_data is not None else {"nodes": "node1", "concepts": [], "past_decisions": []}
    run.llm_called = llm_called
    run.tasks_executed = tasks_executed
    run.final_response = response
    run.intent = "ops"
    return run


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 — retrieve_relevant_nodes
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrieveRelevantNodes:
    def test_returns_dict_with_required_keys(self, tmp_path):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.get_relevant_context.return_value = "some context"
            mock_ks.return_value.search_knowledge.return_value = [
                {"content": "insight A"}
            ]
            mock_mi.return_value.get_relevant_memories.return_value = [
                {"text": "memory 1", "importance": 0.7}
            ]
            result = retrieve_relevant_nodes("test query")

        assert "nodes" in result
        assert "concepts" in result
        assert "past_decisions" in result

    def test_nodes_come_from_knowledge_store(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.get_relevant_context.return_value = "KS context"
            mock_ks.return_value.search_knowledge.return_value = []
            mock_mi.return_value.get_relevant_memories.return_value = []
            result = retrieve_relevant_nodes("query")

        assert result["nodes"] == "KS context"

    def test_past_decisions_from_memory_index(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = []
            mock_mi.return_value.get_relevant_memories.return_value = [
                {"text": "past decision A", "importance": 0.8}
            ]
            result = retrieve_relevant_nodes("query")

        assert len(result["past_decisions"]) == 1
        assert result["past_decisions"][0]["text"] == "past decision A"

    def test_knowledge_store_failure_is_non_fatal(self):
        with patch("core.knowledge_store.get_knowledge_store", side_effect=ImportError("missing")), \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_mi.return_value.get_relevant_memories.return_value = []
            result = retrieve_relevant_nodes("query")

        assert result["nodes"] == ""
        assert isinstance(result["concepts"], list)

    def test_memory_index_failure_is_non_fatal(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index", side_effect=ImportError("missing")):
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = []
            result = retrieve_relevant_nodes("query")

        assert isinstance(result["past_decisions"], list)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2b — build_context
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildContext:
    def test_includes_nodes_section(self):
        ctx = build_context("q", {"nodes": "node_text", "concepts": [], "past_decisions": []})
        assert "Knowledge Graph Context" in ctx
        assert "node_text" in ctx

    def test_includes_concepts_section(self):
        ctx = build_context("q", {"nodes": "", "concepts": ["A", "B"], "past_decisions": []})
        assert "Related Concepts" in ctx
        assert "- A" in ctx

    def test_includes_past_decisions(self):
        ctx = build_context("q", {"nodes": "", "concepts": [], "past_decisions": [{"text": "past1"}]})
        assert "Past Decisions" in ctx
        assert "past1" in ctx

    def test_empty_graph_data_returns_empty_string(self):
        ctx = build_context("q", {"nodes": "", "concepts": [], "past_decisions": []})
        assert ctx == ""

    def test_all_sections_combined(self):
        graph_data = {
            "nodes": "node_ctx",
            "concepts": ["concept_x"],
            "past_decisions": [{"text": "past_decision_y"}],
        }
        ctx = build_context("q", graph_data)
        assert "Knowledge Graph Context" in ctx
        assert "Related Concepts" in ctx
        assert "Past Decisions" in ctx


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — classify_decision
# ══════════════════════════════════════════════════════════════════════════════

class TestClassifyDecision:
    def test_returns_required_keys(self):
        with patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de:
            mock_orch.return_value.classify_intent.return_value = "email"
            mock_action = MagicMock()
            mock_action.skill = "email-marketing"
            mock_action.score = 7.5
            mock_de.return_value.rank_actions.return_value = [mock_action]

            result = classify_decision("send email campaign", {})

        assert "intent" in result
        assert "selected_agents" in result
        assert "execution_plan" in result

    def test_intent_from_orchestrator(self):
        with patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de:
            mock_orch.return_value.classify_intent.return_value = "finance"
            mock_action = MagicMock(skill="finance-wizard", score=8.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]

            result = classify_decision("create financial model", {})

        assert result["intent"] == "finance"

    def test_selected_agents_from_decision_engine(self):
        with patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de:
            mock_orch.return_value.classify_intent.return_value = "content"
            mock_action = MagicMock(skill="content-calendar", score=7.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]

            result = classify_decision("write blog post", {})

        assert "content-calendar" in result["selected_agents"]

    def test_orchestrator_failure_falls_back_gracefully(self):
        with patch("core.orchestrator.TaskOrchestrator", side_effect=ImportError), \
             patch("core.decision_engine.get_decision_engine") as mock_de:
            mock_action = MagicMock(skill="task-orchestrator", score=5.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]

            result = classify_decision("do something", {})

        assert result["intent"] == "ops"

    def test_decision_engine_failure_falls_back_gracefully(self):
        with patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine", side_effect=ImportError):
            mock_orch.return_value.classify_intent.return_value = "ops"

            result = classify_decision("do something", {})

        assert len(result["selected_agents"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Phase 5 — decompose_to_tasks
# ══════════════════════════════════════════════════════════════════════════════

class TestDecomposeToTasks:
    def test_returns_list(self):
        tasks = decompose_to_tasks("LLM output text", "ops", ["task-orchestrator"])
        assert isinstance(tasks, list)
        assert len(tasks) >= 1

    def test_task_has_required_fields(self):
        tasks = decompose_to_tasks("some output", "lead_gen", ["lead-hunter-elite"])
        task = tasks[0]
        assert "agent" in task
        assert "action" in task
        assert "intent" in task
        assert "inputs" in task

    def test_agent_from_selected_agents(self):
        tasks = decompose_to_tasks("output", "email", ["email-marketing"])
        assert tasks[0]["agent"] == "email-marketing"

    def test_empty_agents_uses_fallback(self):
        tasks = decompose_to_tasks("output", "ops", [])
        assert tasks[0]["agent"] == "task-orchestrator"

    def test_intent_preserved_in_task(self):
        tasks = decompose_to_tasks("output", "social", ["social-media-manager"])
        assert tasks[0]["intent"] == "social"

    def test_action_truncated_to_500_chars(self):
        long_output = "x" * 1000
        tasks = decompose_to_tasks(long_output, "ops", ["task-orchestrator"])
        assert len(tasks[0]["action"]) <= 500


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6 — execute_tasks
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteTasks:
    def test_empty_tasks_returns_empty_list(self):
        assert execute_tasks([], "some goal") == []

    def test_empty_goal_returns_empty_list(self):
        tasks = [{"agent": "task-orchestrator", "action": "do something", "intent": "ops", "inputs": {}}]
        assert execute_tasks(tasks, "") == []

    def test_agent_controller_results_mapped(self):
        with patch("core.agent_controller.get_agent_controller") as mock_ctrl:
            mock_ctrl.return_value.run_goal.return_value = {
                "tasks": [
                    {"task_id": "t1", "skill": "problem-solver", "status": "success",
                     "success": True, "score": 0.9, "output": {"text": "done"}}
                ]
            }
            tasks = [{"agent": "problem-solver", "action": "run", "intent": "ops", "inputs": {}}]
            results = execute_tasks(tasks, "do the task")

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["skill"] == "problem-solver"

    def test_agent_controller_failure_returns_skipped(self):
        with patch("core.agent_controller.get_agent_controller", side_effect=ImportError):
            tasks = [{"agent": "task-orchestrator", "action": "run", "intent": "ops", "inputs": {}}]
            results = execute_tasks(tasks, "do the task")

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert results[0]["success"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7 — format_response
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatResponse:
    def test_returns_llm_output_when_no_agent_results(self):
        response = format_response("LLM answer", [], "task-orchestrator")
        assert "LLM answer" in response

    def test_appends_successful_task_results(self):
        results = [{"success": True, "output": {"text": "task result info"}, "skill": "x"}]
        response = format_response("base response", results, "task-orchestrator")
        assert "task result info" in response

    def test_skips_failed_task_results(self):
        results = [{"success": False, "output": {"text": "failed output"}, "skill": "x"}]
        response = format_response("base response", results, "task-orchestrator")
        assert "failed output" not in response

    def test_no_duplicate_content(self):
        # If task output is already in LLM output, it should not be appended
        results = [{"success": True, "output": "base response content", "skill": "x"}]
        response = format_response("base response content here", results, "task-orchestrator")
        assert response.count("base response") <= 2  # not indefinitely duplicated

    def test_schema_validator_fallback_used_on_validation_failure(self):
        with patch("core.agent_output_schemas.get_schema_validator") as mock_sv:
            mock_sv.return_value.validate_or_fallback.return_value = (None, "safe_fallback")
            response = format_response("original output", [], "some-agent")
        assert response == "safe_fallback"

    def test_schema_validator_failure_is_non_fatal(self):
        with patch("core.agent_output_schemas.get_schema_validator", side_effect=ImportError):
            response = format_response("original output", [], "some-agent")
        assert "original output" in response


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8 — update_graph
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateGraph:
    def test_knowledge_store_updated(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.add_memory.return_value = {}

            update_graph("user input", "email", "AI response", [])

        mock_ks.return_value.add_knowledge.assert_called_once()
        mock_ks.return_value.learn_from_conversation.assert_called_once_with("user input")

    def test_memory_index_updated(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}

            update_graph("user input", "email", "AI response", [])

        mock_mi.return_value.add_memory.assert_called_once()

    def test_knowledge_store_failure_is_non_fatal(self):
        with patch("core.knowledge_store.get_knowledge_store", side_effect=RuntimeError("ks error")), \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_mi.return_value.add_memory.return_value = {}
            update_graph("user input", "email", "AI response", [])  # must not raise

    def test_memory_index_failure_is_non_fatal(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index", side_effect=RuntimeError("mi error")):
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            update_graph("user input", "email", "AI response", [])  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# Phase 9 — monitor_and_improve
# ══════════════════════════════════════════════════════════════════════════════

class TestMonitorAndImprove:
    def test_forge_submit_called(self):
        with patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_forge.return_value.submit_change.return_value = MagicMock(id="fcr-1")
            mock_audit.return_value.record.return_value = None

            run = _run()
            monitor_and_improve(run)

        mock_forge.return_value.submit_change.assert_called_once()

    def test_audit_engine_called(self):
        with patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_forge.return_value.submit_change.return_value = MagicMock()
            mock_audit.return_value.record.return_value = None

            run = _run()
            monitor_and_improve(run)

        mock_audit.return_value.record.assert_called_once()
        call_kwargs = mock_audit.return_value.record.call_args[1]
        assert call_kwargs["action"] == "pipeline_run"

    def test_forge_failure_is_non_fatal(self):
        with patch("core.ascend_forge.get_ascend_forge_executor", side_effect=ImportError), \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_audit.return_value.record.return_value = None
            run = _run()
            monitor_and_improve(run)  # must not raise

    def test_audit_failure_is_non_fatal(self):
        with patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine", side_effect=ImportError):
            mock_forge.return_value.submit_change.return_value = MagicMock()
            run = _run()
            monitor_and_improve(run)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# Phase 10 — validate_pipeline_integrity
# ══════════════════════════════════════════════════════════════════════════════

class TestValidatePipelineIntegrity:
    def test_passes_when_all_stages_ran(self):
        run = _run(
            graph_data={"nodes": "some context", "concepts": [], "past_decisions": []},
            llm_called=True,
            tasks_executed=1,
            response="A real answer",
        )
        # Should not raise
        validate_pipeline_integrity(run)

    def test_raises_when_graph_empty(self):
        run = _run(
            graph_data={"nodes": "", "concepts": [], "past_decisions": []},
            llm_called=True,
            tasks_executed=1,
            response="A real answer",
        )
        with pytest.raises(PipelineViolationError, match="graph_nodes_retrieved=0"):
            validate_pipeline_integrity(run)

    def test_raises_when_llm_not_called(self):
        run = _run(llm_called=False, tasks_executed=1, response="A real answer")
        with pytest.raises(PipelineViolationError, match="llm_called=False"):
            validate_pipeline_integrity(run)

    def test_raises_when_no_tasks_executed(self):
        run = _run(llm_called=True, tasks_executed=0, response="A real answer")
        with pytest.raises(PipelineViolationError, match="tasks_executed=0"):
            validate_pipeline_integrity(run)

    def test_raises_when_response_is_fallback(self):
        run = _run(
            llm_called=True,
            tasks_executed=1,
            response=f"{_FALLBACK_PREFIX} something went wrong",
        )
        with pytest.raises(PipelineViolationError, match="response=fallback"):
            validate_pipeline_integrity(run)

    def test_multiple_violations_in_one_error(self):
        run = _run(
            graph_data={"nodes": "", "concepts": [], "past_decisions": []},
            llm_called=False,
            tasks_executed=0,
            response=f"{_FALLBACK_PREFIX} error",
        )
        with pytest.raises(PipelineViolationError) as exc_info:
            validate_pipeline_integrity(run)
        msg = str(exc_info.value)
        assert "graph" in msg
        assert "llm" in msg

    def test_audit_engine_called_on_violation(self):
        with patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_audit.return_value.record.return_value = None
            run = _run(
                graph_data={"nodes": "", "concepts": [], "past_decisions": []},
                llm_called=False,
                tasks_executed=0,
                response="A real answer",
            )
            with pytest.raises(PipelineViolationError):
                validate_pipeline_integrity(run)

        mock_audit.return_value.record.assert_called_once()
        call_kwargs = mock_audit.return_value.record.call_args[1]
        assert call_kwargs["action"] == "pipeline_violation"

    def test_past_decisions_count_as_graph_data(self):
        run = _run(
            graph_data={
                "nodes": "",
                "concepts": [],
                "past_decisions": [{"text": "past decision 1", "importance": 0.5}],
            },
            llm_called=True,
            tasks_executed=1,
            response="A real answer",
        )
        # Should not raise — past_decisions counts as graph data
        validate_pipeline_integrity(run)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1 — process_user_input (integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessUserInput:
    """Integration tests for the full pipeline entry point."""

    def _make_llm_fn(self, response: str = "Agent: task-orchestrator\n\nHello world"):
        def _fn(msg, agent, mode, *, model_route="", user_id="default", graph_context=""):
            return response
        return _fn

    def test_returns_string(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            self._setup_mocks(mock_ks, mock_mi, mock_orch, mock_de, mock_ctrl, mock_forge, mock_audit)

            result = process_user_input(
                "hello",
                generate_llm_response_fn=self._make_llm_fn(),
            )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_graph_context_injected_into_llm_call(self):
        received_context: list[str] = []

        def _llm_fn(msg, agent, mode, *, model_route="", user_id="default", graph_context=""):
            received_context.append(graph_context)
            return "Agent: task-orchestrator\n\nresponse"

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_ks.return_value.get_relevant_context.return_value = "relevant knowledge"
            mock_ks.return_value.search_knowledge.return_value = []
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.get_relevant_memories.return_value = []
            mock_mi.return_value.add_memory.return_value = {}
            mock_orch.return_value.classify_intent.return_value = "ops"
            mock_action = MagicMock(skill="task-orchestrator", score=5.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]
            mock_ctrl.return_value.run_goal.return_value = {"tasks": []}
            mock_forge.return_value.submit_change.return_value = MagicMock()
            mock_audit.return_value.record.return_value = None

            process_user_input("query about sales", generate_llm_response_fn=_llm_fn)

        assert len(received_context) == 1
        # Graph context should contain the KnowledgeStore output
        assert "relevant knowledge" in received_context[0]

    def test_no_llm_fn_still_returns_string(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            self._setup_mocks(mock_ks, mock_mi, mock_orch, mock_de, mock_ctrl, mock_forge, mock_audit)

            result = process_user_input("hello", generate_llm_response_fn=None)

        assert isinstance(result, str)

    def test_pipeline_violation_does_not_surface_to_caller(self):
        """Integrity violations must be logged but must never crash the response."""
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            # Set up empty graph so that integrity check fires violations
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = []
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.get_relevant_memories.return_value = []
            mock_mi.return_value.add_memory.return_value = {}
            mock_orch.return_value.classify_intent.return_value = "ops"
            mock_action = MagicMock(skill="task-orchestrator", score=5.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]
            mock_ctrl.return_value.run_goal.return_value = {"tasks": []}
            mock_forge.return_value.submit_change.return_value = MagicMock()
            mock_audit.return_value.record.return_value = None

            # LLM returns a fallback string — guaranteed to trigger violations
            def _fallback_llm(msg, agent, mode, **kw):
                return f"{_FALLBACK_PREFIX} error"

            # Must not raise
            result = process_user_input("test", generate_llm_response_fn=_fallback_llm)

        assert isinstance(result, str)

    def test_route_to_agent_fn_used_when_provided(self):
        called_with: list[str] = []

        def _custom_route(msg: str) -> str:
            called_with.append(msg)
            return "custom-agent"

        def _llm_fn(msg, agent, mode, *, model_route="", user_id="default", graph_context=""):
            return f"Agent: {agent}\n\nresponse"

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            self._setup_mocks(mock_ks, mock_mi, mock_orch, mock_de, mock_ctrl, mock_forge, mock_audit)

            process_user_input(
                "query",
                generate_llm_response_fn=_llm_fn,
                route_to_agent_fn=_custom_route,
            )

        assert "query" in called_with

    def test_graph_updated_after_response(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            self._setup_mocks(mock_ks, mock_mi, mock_orch, mock_de, mock_ctrl, mock_forge, mock_audit)
            mock_ks.return_value.get_relevant_context.return_value = "context"

            process_user_input(
                "query",
                generate_llm_response_fn=self._make_llm_fn("Agent: t\n\nok"),
            )

        # KnowledgeStore and MemoryIndex should have been written back
        mock_ks.return_value.add_knowledge.assert_called()
        mock_mi.return_value.add_memory.assert_called()

    def _setup_mocks(
        self,
        mock_ks: Any,
        mock_mi: Any,
        mock_orch: Any,
        mock_de: Any,
        mock_ctrl: Any,
        mock_forge: Any,
        mock_audit: Any,
    ) -> None:
        mock_ks.return_value.get_relevant_context.return_value = "context data"
        mock_ks.return_value.search_knowledge.return_value = []
        mock_ks.return_value.add_knowledge.return_value = {}
        mock_ks.return_value.learn_from_conversation.return_value = {}
        mock_mi.return_value.get_relevant_memories.return_value = []
        mock_mi.return_value.add_memory.return_value = {}
        mock_orch.return_value.classify_intent.return_value = "ops"
        mock_action = MagicMock(skill="task-orchestrator", score=5.0)
        mock_de.return_value.rank_actions.return_value = [mock_action]
        mock_ctrl.return_value.run_goal.return_value = {"tasks": []}
        mock_forge.return_value.submit_change.return_value = MagicMock()
        mock_audit.return_value.record.return_value = None

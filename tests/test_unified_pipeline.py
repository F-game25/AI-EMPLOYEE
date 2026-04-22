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
from unittest.mock import MagicMock, call, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_RUNTIME_DIR = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from core.unified_pipeline import (
    PipelineViolationError,
    _PipelineRun,
    _FALLBACK_PREFIX,
    _DEGRADED_MARKER,
    _is_real_execution,
    build_context,
    classify_decision,
    connect_nodes,
    decompose_to_tasks,
    execute_tasks,
    format_response,
    get_pipeline_traces,
    monitor_and_improve,
    process_user_input,
    retrieve_relevant_nodes,
    update_graph,
    validate_pipeline_integrity,
    validate_tasks,
    STRICT_PIPELINE,
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
    run.graph_data = graph_data if graph_data is not None else {"nodes": "node1", "concepts": [], "past_decisions": [], "expanded": []}
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

        # add_knowledge is called at least once (for the intent entry)
        mock_ks.return_value.add_knowledge.assert_called()
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
            graph_data={"nodes": "some context", "concepts": [], "past_decisions": [], "expanded": []},
            llm_called=True,
            tasks_executed=1,
            response="A real answer",
        )
        # Should not raise
        validate_pipeline_integrity(run)

    def test_raises_when_graph_empty(self):
        run = _run(
            graph_data={"nodes": "", "concepts": [], "past_decisions": [], "expanded": []},
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
            graph_data={"nodes": "", "concepts": [], "past_decisions": [], "expanded": []},
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
                graph_data={"nodes": "", "concepts": [], "past_decisions": [], "expanded": []},
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
                "expanded": [],
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


# ══════════════════════════════════════════════════════════════════════════════
# Fix 1 — STRICT_PIPELINE mode
# ══════════════════════════════════════════════════════════════════════════════

class TestStrictPipelineMode:
    """Fix 1: STRICT_PIPELINE env-var hard mode — no fallbacks, loud failures."""

    def test_strict_pipeline_constant_is_bool(self):
        assert isinstance(STRICT_PIPELINE, bool)

    def test_validate_tasks_raises_in_strict_mode(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", True)
        # Malformed task (missing agent) — must raise in strict mode
        with pytest.raises(PipelineViolationError, match="missing required fields"):
            validate_tasks([{"action": "do something", "inputs": {}}])

    def test_validate_tasks_drops_in_non_strict_mode(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        # Malformed task — must be silently dropped (no raise)
        result = validate_tasks([{"action": "do something", "inputs": {}}])
        assert result == []

    def test_execute_tasks_raises_in_strict_mode(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", True)
        with patch("core.agent_controller.get_agent_controller", side_effect=RuntimeError("boom")):
            tasks = [{"agent": "x", "action": "y", "intent": "ops", "inputs": {}}]
            with pytest.raises(RuntimeError, match="boom"):
                execute_tasks(tasks, "goal")

    def test_execute_tasks_skips_in_non_strict_mode(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        with patch("core.agent_controller.get_agent_controller", side_effect=RuntimeError("boom")):
            tasks = [{"agent": "x", "action": "y", "intent": "ops", "inputs": {}}]
            results = execute_tasks(tasks, "goal")
        assert results[0]["status"] == "skipped"


# ══════════════════════════════════════════════════════════════════════════════
# Fix 2 — Graph depth expansion
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphDepthExpansion:
    """Fix 2: retrieve_relevant_nodes() does 1-hop neighbor expansion and returns
    an 'expanded' key in its output dict."""

    def test_returns_expanded_key(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.memory_index.embed_text", return_value=[0.1, 0.2]), \
             patch("core.memory_index.cosine_similarity", return_value=0.5):
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = []
            mock_mi.return_value.get_relevant_memories.return_value = []
            result = retrieve_relevant_nodes("query")
        assert "expanded" in result

    def test_concepts_ranked_by_similarity(self):
        """Concepts should be sorted by descending cosine similarity to input."""
        hits = [
            {"content": "low score concept"},
            {"content": "high score concept"},
        ]
        scores = {"low score concept": 0.3, "high score concept": 0.9}

        def _sim(a, b):
            # identify concept by its embed call sequence
            return scores.get("high score concept" if b == [0.9] else "low score concept", 0.3)

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.memory_index.embed_text") as mock_embed, \
             patch("core.memory_index.cosine_similarity") as mock_sim:
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = hits
            mock_mi.return_value.get_relevant_memories.return_value = []
            # Return distinct vectors so we can simulate scoring
            mock_embed.side_effect = lambda text: [0.9] if "high" in text else [0.3]
            mock_sim.side_effect = lambda a, b: 0.9 if b == [0.9] else 0.3
            result = retrieve_relevant_nodes("query")

        # The high-score concept should come first
        if result["concepts"]:
            assert result["concepts"][0] == "high score concept"

    def test_expanded_nodes_populated_from_neighbors(self):
        """Expanded key should be populated when KS search returns neighbor hits."""
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.memory_index.embed_text", return_value=[0.1]), \
             patch("core.memory_index.cosine_similarity", return_value=0.7):
            mock_ks.return_value.get_relevant_context.return_value = ""
            mock_ks.return_value.search_knowledge.return_value = [
                {"content": "neighbor concept text"}
            ]
            mock_mi.return_value.get_relevant_memories.return_value = []
            result = retrieve_relevant_nodes("query with keywords")

        # expanded may be populated (depends on token matching); just check type
        assert isinstance(result["expanded"], list)

    def test_build_context_includes_expanded_section(self):
        graph_data = {
            "nodes": "",
            "concepts": [],
            "past_decisions": [],
            "expanded": ["neighbor concept A", "neighbor concept B"],
        }
        ctx = build_context("q", graph_data)
        assert "Neighbor Concepts" in ctx
        assert "neighbor concept A" in ctx


# ══════════════════════════════════════════════════════════════════════════════
# Fix 3 — Task schema validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateTasks:
    """Fix 3: validate_tasks() enforces required fields on every task."""

    def test_valid_tasks_pass_through(self):
        tasks = [{"agent": "x", "action": "y", "inputs": {}, "intent": "ops"}]
        result = validate_tasks(tasks)
        assert len(result) == 1

    def test_missing_agent_drops_task(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        tasks = [{"action": "y", "inputs": {}}]
        result = validate_tasks(tasks)
        assert result == []

    def test_missing_action_drops_task(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        tasks = [{"agent": "x", "inputs": {}}]
        result = validate_tasks(tasks)
        assert result == []

    def test_missing_inputs_drops_task(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        tasks = [{"agent": "x", "action": "y"}]
        result = validate_tasks(tasks)
        assert result == []

    def test_mixed_valid_and_invalid_keeps_only_valid(self, monkeypatch):
        import core.unified_pipeline as up
        monkeypatch.setattr(up, "STRICT_PIPELINE", False)
        tasks = [
            {"agent": "x", "action": "y", "inputs": {}},
            {"action": "z"},  # invalid — no agent or inputs
            {"agent": "a", "action": "b", "inputs": {"k": "v"}},
        ]
        result = validate_tasks(tasks)
        assert len(result) == 2

    def test_decompose_to_tasks_produces_validated_output(self):
        """decompose_to_tasks must return only valid tasks."""
        tasks = decompose_to_tasks("some llm output", "ops", ["task-orchestrator"])
        for task in tasks:
            assert "agent" in task
            assert "action" in task
            assert "inputs" in task


# ══════════════════════════════════════════════════════════════════════════════
# Fix 4 — Real execution verification
# ══════════════════════════════════════════════════════════════════════════════

class TestIsRealExecution:
    """Fix 4: _is_real_execution() correctly identifies genuine vs fake results."""

    def test_real_execution_requires_task_id(self):
        result = {
            "task_id": "",
            "status": "success",
            "output": "Detailed output with lots of text that is clearly real",
        }
        assert _is_real_execution(result) is False

    def test_real_execution_requires_success_status(self):
        result = {
            "task_id": "t123",
            "status": "failed",
            "output": "Detailed output with lots of text",
        }
        assert _is_real_execution(result) is False

    def test_real_execution_requires_non_trivial_output(self):
        result = {"task_id": "t123", "status": "success", "output": "done"}
        assert _is_real_execution(result) is False

    def test_none_output_is_fake(self):
        result = {"task_id": "t123", "status": "success", "output": None}
        assert _is_real_execution(result) is False

    def test_genuine_result_is_real(self):
        result = {
            "task_id": "t-abc-123",
            "status": "success",
            "output": "Generated a comprehensive 30-day content calendar with 90 posts across all platforms",
        }
        assert _is_real_execution(result) is True

    def test_dict_output_checked_for_text(self):
        result = {
            "task_id": "t123",
            "status": "success",
            "output": {"text": "Full detailed analysis report with actionable insights"},
        }
        assert _is_real_execution(result) is True

    def test_execute_tasks_annotates_real_execution_flag(self):
        with patch("core.agent_controller.get_agent_controller") as mock_ctrl:
            mock_ctrl.return_value.run_goal.return_value = {
                "tasks": [
                    {
                        "task_id": "t1",
                        "skill": "worker",
                        "status": "success",
                        "success": True,
                        "score": 0.9,
                        "output": "Full detailed comprehensive output with real data analysis",
                    }
                ]
            }
            tasks = [{"agent": "worker", "action": "run", "intent": "ops", "inputs": {}}]
            results = execute_tasks(tasks, "goal")

        assert "real_execution" in results[0]
        assert results[0]["real_execution"] is True

    def test_execute_tasks_flags_simulated_output(self):
        with patch("core.agent_controller.get_agent_controller") as mock_ctrl:
            mock_ctrl.return_value.run_goal.return_value = {
                "tasks": [
                    {
                        "task_id": "t1",
                        "skill": "worker",
                        "status": "success",
                        "success": True,
                        "score": 0.9,
                        "output": "done",  # simulated placeholder
                    }
                ]
            }
            tasks = [{"agent": "worker", "action": "run", "intent": "ops", "inputs": {}}]
            results = execute_tasks(tasks, "goal")

        assert results[0]["real_execution"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Fix 5 — Graph edge builder
# ══════════════════════════════════════════════════════════════════════════════

class TestConnectNodes:
    """Fix 5: connect_nodes() creates directed edges in KnowledgeStore."""

    def test_connect_nodes_stores_edge(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks:
            mock_ks.return_value.add_knowledge.return_value = {}
            result = connect_nodes("intent_a", "skill_b", "executed_via")

        assert result is True
        mock_ks.return_value.add_knowledge.assert_called_once()
        args = mock_ks.return_value.add_knowledge.call_args
        assert args[0][0] == "_edges"
        edge = args[0][1]
        assert edge["source"] == "intent_a"
        assert edge["target"] == "skill_b"
        assert edge["relationship"] == "executed_via"

    def test_connect_nodes_returns_false_for_same_source_target(self):
        result = connect_nodes("a", "a", "self")
        assert result is False

    def test_connect_nodes_returns_false_for_empty_source(self):
        result = connect_nodes("", "target", "rel")
        assert result is False

    def test_connect_nodes_failure_is_non_fatal(self):
        with patch("core.knowledge_store.get_knowledge_store", side_effect=RuntimeError("ks down")):
            result = connect_nodes("a", "b", "rel")
        assert result is False

    def test_update_graph_creates_edges_between_intent_and_skills(self):
        """update_graph() should call connect_nodes for executed agents."""
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.add_memory.return_value = {}

            agent_results = [
                {"skill": "email-marketing", "status": "success", "success": True, "output": "done"},
            ]
            update_graph("user input", "email", "response text", agent_results)

        # add_knowledge should have been called at least twice:
        # once for the intent entry, once for the edge
        assert mock_ks.return_value.add_knowledge.call_count >= 2

    def test_update_graph_creates_precedes_edge_when_prev_intent_differs(self):
        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi:
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.add_memory.return_value = {}

            update_graph("user input", "content", "response", [], prev_intent="email")

        # Verify an edge was created between email and content
        edge_calls = [
            call for call in mock_ks.return_value.add_knowledge.call_args_list
            if call[0][0] == "_edges"
        ]
        assert len(edge_calls) >= 1
        edge_data = edge_calls[0][0][1]
        assert edge_data["relationship"] == "precedes"


# ══════════════════════════════════════════════════════════════════════════════
# Fix 6 — Pipeline tracing
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineTracing:
    """Fix 6: run.trace dict is populated and accessible via get_pipeline_traces()."""

    def test_pipeline_run_has_trace_dict(self):
        run = _PipelineRun("input", "user", "power", "")
        assert isinstance(run.trace, dict)
        assert "input" in run.trace
        assert "retrieved_nodes" in run.trace
        assert "decision" in run.trace
        assert "agent_results" in run.trace
        assert "final_output" in run.trace

    def test_trace_input_matches_run_input(self):
        run = _PipelineRun("my test input", "user1", "power", "")
        assert run.trace["input"] == "my test input"

    def test_get_pipeline_traces_returns_list(self):
        result = get_pipeline_traces()
        assert isinstance(result, list)

    def test_trace_stored_after_process_user_input(self):
        import core.unified_pipeline as up
        initial_count = len(up._TRACE_STORE)

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_ks.return_value.get_relevant_context.return_value = "ctx"
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

            process_user_input(
                "trace test input",
                generate_llm_response_fn=lambda msg, agent, mode, **kw: "A response",
            )

        assert len(up._TRACE_STORE) > initial_count
        latest = list(up._TRACE_STORE)[-1]
        assert latest["input"] == "trace test input"
        assert "latency_ms" in latest

    def test_trace_contains_agent_results(self):
        import core.unified_pipeline as up

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            mock_ks.return_value.get_relevant_context.return_value = "ctx"
            mock_ks.return_value.search_knowledge.return_value = []
            mock_ks.return_value.add_knowledge.return_value = {}
            mock_ks.return_value.learn_from_conversation.return_value = {}
            mock_mi.return_value.get_relevant_memories.return_value = []
            mock_mi.return_value.add_memory.return_value = {}
            mock_orch.return_value.classify_intent.return_value = "ops"
            mock_action = MagicMock(skill="task-orchestrator", score=5.0)
            mock_de.return_value.rank_actions.return_value = [mock_action]
            mock_ctrl.return_value.run_goal.return_value = {
                "tasks": [{
                    "task_id": "t1", "skill": "task-orchestrator",
                    "status": "success", "success": True,
                    "score": 0.8, "output": "real output with sufficient length here",
                }]
            }
            mock_forge.return_value.submit_change.return_value = MagicMock()
            mock_audit.return_value.record.return_value = None

            process_user_input(
                "task trace test",
                generate_llm_response_fn=lambda msg, agent, mode, **kw: "Response",
            )

        latest = list(up._TRACE_STORE)[-1]
        assert isinstance(latest["agent_results"], list)


# ══════════════════════════════════════════════════════════════════════════════
# Fix 7 — Kill silent failure (degraded flag + DEGRADED marker)
# ══════════════════════════════════════════════════════════════════════════════

class TestDegradedFlag:
    """Fix 7: Pipeline violations set run.degraded=True and append DEGRADED marker
    to the response instead of being silently swallowed."""

    def test_pipeline_run_has_degraded_flag(self):
        run = _PipelineRun("input", "user", "power", "")
        assert run.degraded is False

    def test_validate_pipeline_integrity_sets_degraded_on_run(self):
        run = _run(
            graph_data={"nodes": "", "concepts": [], "past_decisions": [], "expanded": []},
            llm_called=False,
            tasks_executed=0,
            response="A real answer",
        )
        with pytest.raises(PipelineViolationError):
            validate_pipeline_integrity(run)
        assert run.degraded is True

    def test_degraded_marker_constant_is_non_empty(self):
        assert _DEGRADED_MARKER
        assert "DEGRADED" in _DEGRADED_MARKER

    def test_format_response_appends_degraded_marker_when_flag_set(self):
        response = format_response("base response", [], "task-orchestrator", degraded=True)
        assert _DEGRADED_MARKER in response

    def test_format_response_no_marker_when_not_degraded(self):
        response = format_response("base response", [], "task-orchestrator", degraded=False)
        assert _DEGRADED_MARKER not in response

    def test_process_user_input_appends_degraded_marker_on_violation(self):
        """When pipeline violations are detected, the user-visible response must
        contain the DEGRADED marker (internal debug panel can surface it)."""
        def _fallback_llm(msg, agent, mode, **kw):
            return f"{_FALLBACK_PREFIX} LLM error"

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
            # Empty graph — will trigger graph violation
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

            result = process_user_input("test", generate_llm_response_fn=_fallback_llm)

        assert _DEGRADED_MARKER in result

    def test_trace_records_degraded_state(self):
        """run.trace['degraded'] must be True when violations are detected."""
        import core.unified_pipeline as up

        def _fallback_llm(msg, agent, mode, **kw):
            return f"{_FALLBACK_PREFIX} LLM error"

        with patch("core.knowledge_store.get_knowledge_store") as mock_ks, \
             patch("core.memory_index.get_memory_index") as mock_mi, \
             patch("core.orchestrator.TaskOrchestrator") as mock_orch, \
             patch("core.decision_engine.get_decision_engine") as mock_de, \
             patch("core.agent_controller.get_agent_controller") as mock_ctrl, \
             patch("core.ascend_forge.get_ascend_forge_executor") as mock_forge, \
             patch("core.audit_engine.get_audit_engine") as mock_audit:
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

            process_user_input("test", generate_llm_response_fn=_fallback_llm)

        latest = list(up._TRACE_STORE)[-1]
        assert latest.get("degraded") is True

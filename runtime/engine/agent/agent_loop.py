"""ReAct agent loop — Reason → Act → Observe cycle.

Iterative agent that selects tools step-by-step based on observations,
rather than building a full task graph upfront. Uses the existing
LLMClient and ToolRegistry interfaces.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("engine.agent.react")

# Per-step model routing — cheapest model that can handle each action class.
# tool-call steps: fast tiny model (llama3.2). analysis/finish: general model.
# code actions: coder model. These are overridden by ResourceManager at runtime.
_STEP_MODELS: dict[str, str] = {
    "tool": "llama3.2",          # routing / tool-call reasoning
    "analysis": "gemma3",        # synthesis, research steps
    "code": "qwen2.5-coder:14b", # write/edit code
    "default": "llama3.2",
}

_CODE_TOOLS = {"write_file", "code_exec", "shell_exec"}
_ANALYSIS_TOOLS = {"web_research", "browser_fetch", "llm_infer", "get_memory", "embed_text"}

def _select_step_model(action: str, resource_manager=None) -> str:
    """Pick the cheapest model appropriate for this action."""
    try:
        if resource_manager is not None:
            budget = resource_manager.budget
            stack = {
                "tool": budget.llm_primary,
                "analysis": budget.llm_reasoning or budget.llm_primary,
                "code": budget.llm_coder if budget.can_run_coder else budget.llm_reasoning or budget.llm_primary,
            }
        else:
            stack = _STEP_MODELS
    except Exception:
        stack = _STEP_MODELS

    if action in _CODE_TOOLS:
        return stack.get("code", _STEP_MODELS["code"])
    if action in _ANALYSIS_TOOLS:
        return stack.get("analysis", _STEP_MODELS["analysis"])
    return stack.get("tool", _STEP_MODELS["tool"])


_SYSTEM_PROMPT = """\
You are a ReAct agent. On each step you must output ONLY valid JSON with this structure:
{
  "thought": "<reasoning about what to do next>",
  "action": "<tool_name or 'finish'>",
  "action_input": <dict of inputs for the tool, or the final answer string if action is 'finish'>
}

Rules:
- Choose 'finish' only when you have a complete answer to the goal.
- action_input for 'finish' must be a string containing the final answer.
- For all other actions, action_input must be a dict matching the tool's input schema.
- Never repeat the same action with the same input twice in a row.
- Be concise in thoughts. Prioritize tools that directly address the goal.
"""


@dataclass
class Step:
    step_num: int
    thought: str
    action: str
    action_input: Any
    observation: dict[str, Any]
    duration_ms: float = 0.0


@dataclass
class RunResult:
    run_id: str
    goal: str
    status: str  # "done" | "failed" | "max_steps"
    output: str
    steps: list[Step] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: float = 0.0


class ReActAgent:
    """Iterative Reason-Act-Observe agent loop.

    Args:
        tools:      ToolRegistry instance — tools are looked up and executed here.
        llm:        LLMClient instance — used for reasoning steps.
        max_steps:  Hard cap on iterations (default 15).
        max_risk:   Maximum tool risk level allowed (0-3). Default 2.
        on_step:    Optional callback(step: Step) called after each step completes.
    """

    def __init__(
        self,
        tools,
        llm,
        max_steps: int = 15,
        max_risk: int = 2,
        on_step: Callable[[Step], None] | None = None,
        hitl_approved: bool = False,
        approval_timeout_s: int = 120,
        resource_manager=None,
    ) -> None:
        self.tools = tools
        self.llm = llm
        self.max_steps = max_steps
        self.max_risk = max_risk
        self.on_step = on_step
        self._hitl_approved = hitl_approved
        self._approval_timeout_s = approval_timeout_s
        self._resource_manager = resource_manager
        if resource_manager is None:
            try:
                from engine.compute.resource_manager import get_resource_manager
                self._resource_manager = get_resource_manager()
            except Exception:
                pass

    def run(self, goal: str, context: dict[str, Any] | None = None) -> RunResult:
        run_id = str(uuid.uuid4())
        t_start = time.time()
        steps: list[Step] = []
        total_tokens = 0
        trajectory_text = ""

        available_tools = self.tools.list_tools(max_risk=self.max_risk)
        tool_descriptions = "\n".join(
            f"- {t['name']}: {t['description']}" for t in available_tools
        )

        ctx_block = ""
        if context:
            ctx_block = f"\n\nContext:\n{json.dumps(context, indent=2)}"

        prompt_header = (
            f"Goal: {goal}{ctx_block}\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            "Begin the ReAct loop."
        )

        last_action = "default"
        for step_num in range(1, self.max_steps + 1):
            prompt = prompt_header
            if trajectory_text:
                prompt += f"\n\nTrajectory so far:\n{trajectory_text}"
            prompt += f"\n\nStep {step_num}:"

            step_model = _select_step_model(last_action, self._resource_manager)

            t0 = time.time()
            try:
                completion = self.llm.complete(prompt=prompt, system=_SYSTEM_PROMPT, model=step_model)
                raw = completion.get("output", "").strip()
                total_tokens += int(completion.get("tokens_used", 0))
                if step_num == 1 or step_model != last_action:
                    logger.debug("step %d model=%s", step_num, step_model)
            except Exception as exc:
                logger.error("LLM call failed at step %d: %s", step_num, exc)
                result = RunResult(
                    run_id=run_id, goal=goal, status="failed",
                    output=f"LLM error: {exc}", steps=steps,
                    tokens_used=total_tokens,
                    duration_ms=(time.time() - t_start) * 1000,
                )
                return result

            thought, action, action_input = self._parse_reason(raw)

            if action == "finish":
                final_answer = action_input if isinstance(action_input, str) else json.dumps(action_input)
                steps.append(Step(step_num, thought, action, action_input, {"answer": final_answer}, (time.time() - t0) * 1000))
                return RunResult(
                    run_id=run_id, goal=goal, status="done",
                    output=final_answer, steps=steps,
                    tokens_used=total_tokens,
                    duration_ms=(time.time() - t_start) * 1000,
                )

            obs = self._observe(action, action_input)
            duration_ms = (time.time() - t0) * 1000
            step = Step(step_num, thought, action, action_input, obs, duration_ms)
            steps.append(step)
            last_action = action

            if self.on_step:
                try:
                    self.on_step(step)
                except Exception:
                    pass

            trajectory_text += (
                f"\nThought: {thought}"
                f"\nAction: {action}"
                f"\nAction Input: {json.dumps(action_input)}"
                f"\nObservation: {json.dumps(obs)}\n"
            )

            logger.debug("step %d action=%s ok=%s", step_num, action, obs.get("ok"))

        return RunResult(
            run_id=run_id, goal=goal, status="max_steps",
            output="Reached maximum steps without finishing.",
            steps=steps, tokens_used=total_tokens,
            duration_ms=(time.time() - t_start) * 1000,
        )

    def _parse_reason(self, raw: str) -> tuple[str, str, Any]:
        """Parse LLM output into (thought, action, action_input). Robust to markdown fences."""
        text = raw
        if "```" in text:
            # strip ```json ... ``` or ``` ... ```
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if m:
                text = m.group(1).strip()

        try:
            parsed = json.loads(text)
            thought = str(parsed.get("thought", ""))
            action = str(parsed.get("action", "finish"))
            action_input = parsed.get("action_input", "")
            return thought, action, action_input
        except Exception:
            logger.warning("Could not parse LLM JSON, defaulting to finish. Raw: %s", raw[:200])
            return "Could not parse response.", "finish", raw

    def _observe(self, action: str, action_input: Any) -> dict[str, Any]:
        """Execute tool and return observation dict. Risk-2+ tools go through approval gate."""
        if not isinstance(action_input, dict):
            action_input = {"value": action_input}

        tool_entry = self.tools.get(action)
        if not tool_entry:
            return {"ok": False, "error": f"Unknown tool: {action}. Available: {[t['name'] for t in self.tools.list_tools(self.max_risk)]}"}

        risk = tool_entry.get("risk_level", 0)
        if risk > self.max_risk:
            return {"ok": False, "error": f"Tool '{action}' risk level {risk} exceeds allowed max {self.max_risk}"}

        # Risk-2 tools require human approval (non-blocking with 120s timeout)
        if risk >= 2 and not self._hitl_approved:
            try:
                from core.tool_approval_gate import request_approval
                gate = request_approval(
                    tool_name=action,
                    payload=action_input,
                    agent_id="react_agent",
                    timeout_s=self._approval_timeout_s,
                )
                if not gate["approved"]:
                    return {
                        "ok": False,
                        "approval_required": True,
                        "request_id": gate["request_id"],
                        "status": gate["status"],
                        "error": f"Tool '{action}' requires human approval (status: {gate['status']}). "
                                 "Approve via /api/forge/tools/{request_id}/approve",
                    }
            except ImportError:
                pass  # gate module unavailable — allow through

        return self.tools.execute(action, action_input, agent_id="react_agent")

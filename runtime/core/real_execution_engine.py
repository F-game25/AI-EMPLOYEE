"""Real execution engine — strict loop, no fake results.

Non-negotiable rules enforced here:
  1. Every action maps to a real tool call
  2. Tools return success or error — never simulated success
  3. Results are verified before state update
  4. Loop drives execution step by step
  5. Context from prior steps is passed to later steps
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ExecutionState:
    """Tracks per-task status and output throughout the loop."""

    def __init__(self) -> None:
        self._tasks: dict[int, dict] = {}

    def start(self, task_id: int) -> None:
        self._tasks[task_id] = {"status": "in_progress", "started_at": _now(), "output": None, "error": None}

    def finish(self, task_id: int, result: dict) -> None:
        entry = self._tasks.setdefault(task_id, {})
        entry["status"] = result.get("status", "error")
        entry["output"] = result.get("output")
        entry["error"] = result.get("error", "")
        entry["finished_at"] = _now()

    def get_output(self, task_id: int) -> Any:
        return (self._tasks.get(task_id) or {}).get("output")

    def snapshot(self) -> list[dict]:
        return [
            {"task_id": tid, **data}
            for tid, data in sorted(self._tasks.items())
        ]


class RealExecutionEngine:
    """Executes a structured task plan using the tool registry.

    Loop invariant: for each task
      - get tool from registry (error if missing — no fake)
      - resolve parameter references to prior step outputs
      - execute tool
      - verify result is {"status": "success"|"error", ...}
      - update state
      - if error and not continue_on_error: stop
    """

    def __init__(self) -> None:
        from core.tool_registry import get_tool, list_tools
        self._get_tool = get_tool
        self._list_tools = list_tools

    def run(self, task_plan: list[dict], *, goal: str = "", goal_type: str = "general") -> dict[str, Any]:
        """Execute the full plan and return a structured summary."""
        from core.goal_store import get_goal_store
        store = get_goal_store()
        goal_id = store.create(goal or "unnamed", goal_type, task_plan)
        store.start(goal_id)

        state = ExecutionState()
        results: list[dict] = []
        completed = 0
        failed_at: int | None = None

        logger.info("[ENGINE] Starting execution: goal_id=%s steps=%d goal=%r", goal_id, len(task_plan), goal[:80])

        for task in sorted(task_plan, key=lambda t: int(t.get("id", 0))):
            task_id = int(task.get("id", 0))
            action = task.get("action", "")
            raw_params = task.get("params", {})
            description = task.get("description", action)
            continue_on_error = bool(task.get("continue_on_error", False))

            logger.info("[ENGINE] Step %d: action=%s — %s", task_id, action, description)

            # 1. Map to tool
            tool = self._get_tool(action)
            if tool is None:
                result = {
                    "status": "error",
                    "error": f"no_tool_registered_for_action:{action}",
                    "available_tools": [t["name"] for t in self._list_tools()],
                }
                logger.warning("[ENGINE] Step %d FAILED — no tool for action '%s'", task_id, action)
            else:
                # 2. Resolve $step_N references in params
                resolved_params = _resolve_refs(raw_params, state)

                # 3. Execute tool
                state.start(task_id)
                result = tool.run(resolved_params)

                # 4. Verify result contract
                if not isinstance(result, dict) or result.get("status") not in ("success", "error"):
                    result = {
                        "status": "error",
                        "error": f"tool_violated_contract: got {result!r}",
                    }

            result["task_id"] = task_id
            result["action"] = action

            # 5. Update state
            state.finish(task_id, result)
            results.append(result)

            if result["status"] == "success":
                completed += 1
                logger.info("[ENGINE] Step %d SUCCESS — output keys: %s",
                           task_id, list(result.get("output", {}).keys()) if isinstance(result.get("output"), dict) else type(result.get("output")).__name__)
            else:
                logger.warning("[ENGINE] Step %d ERROR — %s", task_id, result.get("error", "unknown"))
                if not continue_on_error:
                    failed_at = task_id
                    break

        success = failed_at is None
        summary = {
            "goal": goal,
            "goal_id": goal_id,
            "total_steps": len(task_plan),
            "completed": completed,
            "failed_at_step": failed_at,
            "success": success,
            "steps": state.snapshot(),
            "results": results,
        }

        if success:
            store.complete(goal_id, {"completed": completed, "total": len(task_plan)})
        else:
            store.fail(goal_id, f"failed_at_step:{failed_at}")

        logger.info("[ENGINE] Done: goal_id=%s %d/%d steps success=%s", goal_id, completed, len(task_plan), success)
        return summary

    def extract_attachments(self, execution_result: dict) -> list[dict]:
        """Return list of {type, filename, content[, language]} from step outputs."""
        attachments: list[dict] = []
        for step in execution_result.get("results", []):
            output = step.get("output") or {}
            action = step.get("action", "")
            if not isinstance(output, dict):
                continue
            if output.get("html_content"):
                attachments.append({
                    "type": "html",
                    "filename": output.get("filename", "index.html"),
                    "content": output["html_content"],
                })
            elif output.get("content") and output.get("filename"):
                lang = _guess_language(output["filename"])
                attachments.append({
                    "type": "code",
                    "filename": output["filename"],
                    "content": output["content"],
                    "language": lang,
                })
            elif action == "llm_generate" and isinstance(output.get("content"), str):
                attachments.append({
                    "type": "text",
                    "filename": "generated.md",
                    "content": output["content"],
                })
        return attachments

    def format_for_chat(self, execution_result: dict) -> str:
        """Format execution result as a human-readable chat response."""
        steps = execution_result.get("steps", [])
        goal = execution_result.get("goal", "")
        success = execution_result.get("success", False)

        lines: list[str] = []
        if goal:
            lines.append(f"**Goal:** {goal}\n")

        for step in steps:
            sid = step.get("task_id", "?")
            status = step.get("status", "?")
            icon = "✅" if status == "success" else ("⏳" if status == "in_progress" else "❌")
            output = step.get("output")
            error = step.get("error", "")

            line = f"{icon} Step {sid}"
            if isinstance(output, dict):
                if "count" in output:
                    line += f" — {output['count']} item(s) found"
                elif "saved" in output:
                    line += f" — {output['saved']} item(s) saved"
                elif output.get("html_content"):
                    fn = output.get("filename", "index.html")
                    preview = output["html_content"][:200]
                    line += f" — created **{fn}**\n```html\n{preview}…\n```"
                elif output.get("content") and output.get("filename"):
                    fn = output["filename"]
                    lang = _guess_language(fn)
                    preview = str(output["content"])[:200]
                    line += f" — created **{fn}**\n```{lang}\n{preview}…\n```"
                elif output.get("content"):
                    chars = len(str(output["content"]))
                    line += f" — content generated ({chars} chars)"
                elif "path" in output:
                    line += f" — saved to {output['path']}"
                elif "results" in output:
                    line += f" — {len(output['results'])} result(s)"
            elif error:
                line += f" — {error}"
            lines.append(line)

            if status == "error" and isinstance(output, dict) and "required" in output:
                lines.append(f"  → To fix: {output['required']}")

        total = execution_result.get("total_steps", 0)
        done = execution_result.get("completed", 0)
        lines.append(f"\n**{done}/{total} steps completed.** {'Task done.' if success else 'Stopped at first error.'}")

        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".html": "html",
    ".css": "css", ".sh": "bash", ".bash": "bash", ".md": "markdown",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".sql": "sql",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
}


def _guess_language(filename: str) -> str:
    return _LANG_MAP.get(Path(filename).suffix.lower(), "text")


def _resolve_refs(params: Any, state: ExecutionState) -> Any:
    """Replace "$step_N" strings in params with actual outputs from prior steps."""
    if isinstance(params, str):
        match = re.fullmatch(r"\$step_(\d+)", params.strip())
        if match:
            step_id = int(match.group(1))
            output = state.get_output(step_id)
            return _output_to_str(output) if output is not None else params
        return params
    if isinstance(params, dict):
        return {k: _resolve_refs(v, state) for k, v in params.items()}
    if isinstance(params, list):
        return [_resolve_refs(i, state) for i in params]
    return params


def _output_to_str(output: Any) -> Any:
    """Convert tool output to a usable form for the next step."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        # If it's a web search result, stringify the snippets for downstream LLM
        if "results" in output:
            snippets = [r.get("snippet", "") for r in output["results"] if isinstance(r, dict)]
            return "\n".join(snippets)
        if "content" in output:
            return output["content"]
        if "leads" in output:
            return output["leads"]
        return json.dumps(output)
    if isinstance(output, list):
        return json.dumps(output)
    return str(output)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

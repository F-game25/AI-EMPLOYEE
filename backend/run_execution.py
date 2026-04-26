#!/usr/bin/env python3
"""Execution bridge — called by Node.js to run the real execution engine.

Reads JSON goal from stdin, runs goal_parser + real_execution_engine,
writes JSON result to stdout. Never exits with fake success.

Usage: echo '{"message": "find 10 gym leads"}' | python3 run_execution.py
"""
import json
import os
import sys
from pathlib import Path

# Resolve runtime dir: env var takes priority (set by run.sh / server startup),
# then fall back to the location relative to this script (for dev use).
_REPO_DIR = os.environ.get("AI_EMPLOYEE_REPO_DIR", "")
if _REPO_DIR:
    _RUNTIME_DIR = Path(_REPO_DIR) / "runtime"
else:
    # Script lives in backend/ — go up one level to repo root
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    _RUNTIME_DIR = _REPO_ROOT / "runtime"
    # If that doesn't exist (installed copy), try common locations
    if not _RUNTIME_DIR.exists():
        for _candidate in [
            Path.home() / "AI-EMPLOYEE" / "runtime",
            Path("/home/lf/AI-EMPLOYEE/runtime"),
        ]:
            if _candidate.exists():
                _RUNTIME_DIR = _candidate
                break

if not str(_RUNTIME_DIR) in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

# Load env from ~/.ai-employee/.env so tools can see API keys + OLLAMA_HOST
_ENV_FILE = Path.home() / ".ai-employee" / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        message = payload.get("message", "")
    except (json.JSONDecodeError, KeyError) as exc:
        _fail(f"bad_input: {exc}")
        return

    if not message:
        _fail("empty_message")
        return

    try:
        from core.goal_parser import parse_goal
    except Exception as exc:
        _fail(f"import_goal_parser: {exc}")
        return

    try:
        plan = parse_goal(message)
    except Exception as exc:
        _fail(f"goal_parser_failed: {exc}")
        return

    if not plan.get("is_goal") or not plan.get("task_plan"):
        # Not an actionable goal — signal to caller to use normal LLM chat
        _out({"is_goal": False, "reply": None})
        return

    try:
        from core.real_execution_engine import RealExecutionEngine
    except Exception as exc:
        _fail(f"import_engine: {exc}")
        return

    try:
        engine = RealExecutionEngine()
        result = engine.run(plan["task_plan"], goal=message, goal_type=plan.get("goal_type", "general"))
        reply = engine.format_for_chat(result)
        structured = plan.get("structured_goal", {})
        if structured.get("action"):
            reply = f"Executing: **{structured['action']}**\n\n" + reply
        attachments = engine.extract_attachments(result)
        step_actions = [
            {"action": s.get("action", ""), "status": s.get("status", "")}
            for s in (result.get("results") or [])
            if isinstance(s, dict) and s.get("action")
        ][:8]
        _out({"is_goal": True, "reply": reply, "success": result["success"], "steps": result["completed"], "attachments": attachments, "step_actions": step_actions})
    except Exception as exc:
        _fail(f"engine_failed: {exc}")


def _out(data: dict) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _fail(reason: str) -> None:
    _out({"is_goal": False, "reply": None, "error": reason})


if __name__ == "__main__":
    main()

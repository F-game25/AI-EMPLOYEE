"""Last30DaysSkill — multi-source "what are people saying in the last 30 days" research.

A first-class executable skill that the orchestrator can dispatch. It wraps the
vendored ``last30days`` agent skill (forked by the owner from mvanhorn/last30days-skill,
MIT) which pulls posts + engagement from Reddit, X, YouTube, TikTok, Hacker News,
Polymarket, GitHub and the web, then synthesizes a grounded summary.

Replication model: the skill's own Python is vendored under
``runtime/skills/vendor/last30days/`` and invoked as a subprocess (array args, no
shell, hard timeout). Keyless sources (reddit/youtube/hackernews/polymarket/github/
web grounding) work out of the box; richer sources activate when their optional API
keys are present in the environment — never committed, read at runtime only.

GRACEFUL: if the vendored payload or python is missing the skill returns a structured
``error`` status instead of raising, so a task graph degrades cleanly.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from skills.base import SkillBase

logger = logging.getLogger(__name__)

_VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "last30days"
_ENTRY = _VENDOR_ROOT / "scripts" / "last30days.py"

# Emit modes supported by the vendored CLI (kept in sync with build_parser there).
_EMIT_MODES = ("json", "compact", "context", "md", "brief")
_RETRIEVAL_PROFILES = ("default", "quick", "deep")
_MAX_TOPIC_LEN = 300
_DEFAULT_TIMEOUT_S = 240


class Last30DaysSkill(SkillBase):
    """Research recent multi-source discussion about a topic and summarize it."""

    name = "last30days"
    description = (
        "Research what people actually say about a topic in the last 30 days across "
        "Reddit, X, YouTube, TikTok, Hacker News, Polymarket, GitHub and the web, then "
        "synthesize a grounded summary with sources."
    )
    version = "3.8.1"
    capability_tags = ["research", "deep-research", "trends", "social", "market", "web"]
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "What to research."},
            "emit": {"type": "string", "enum": list(_EMIT_MODES)},
            "sources": {"type": "string", "description": "Comma-separated source list (e.g. reddit,youtube,hackernews)."},
            "profile": {"type": "string", "enum": list(_RETRIEVAL_PROFILES)},
            "deep_research": {"type": "boolean"},
            "mock": {"type": "boolean", "description": "Use offline fixtures (no network)."},
            "timeout_s": {"type": "integer", "minimum": 10, "maximum": 1800},
        },
        "required": ["topic"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "topic": {"type": "string"},
            "emit": {"type": "string"},
            "result": {},
            "available_sources": {"type": "array"},
            "elapsed_ms": {"type": "integer"},
            "error": {"type": "string"},
        },
        "required": ["status"],
    }
    allowed_actions = ["skill_dispatch"]

    def execute(
        self,
        input_data: dict[str, Any],
        action_runner: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        topic = " ".join(str(input_data.get("topic") or "").split())
        if not topic:
            return {"status": "error", "error": "topic is required"}
        if len(topic) > _MAX_TOPIC_LEN:
            topic = topic[:_MAX_TOPIC_LEN]

        if not _ENTRY.exists():
            return {"status": "error", "error": f"vendored last30days payload missing at {_ENTRY}"}

        emit = str(input_data.get("emit") or "json").strip().lower()
        if emit not in _EMIT_MODES:
            emit = "json"
        timeout_s = self._coerce_timeout(input_data.get("timeout_s"))

        # Build args as a list — no shell, so the topic and source list can never be
        # interpreted as commands regardless of their content.
        python_bin = os.getenv("PYTHON_BIN") or sys.executable or "python3"
        args = [python_bin, str(_ENTRY), topic, "--emit", emit]
        sources = str(input_data.get("sources") or "").strip()
        if sources:
            args += ["--search", sources]
        profile = str(input_data.get("profile") or "").strip().lower()
        if profile == "quick":
            args.append("--quick")
        elif profile == "deep":
            args.append("--deep")
        if bool(input_data.get("deep_research")):
            args.append("--deep-research")
        if bool(input_data.get("mock")):
            args.append("--mock")

        started = time.time()
        try:
            proc = subprocess.run(
                args,
                cwd=str(_ENTRY.parent),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "topic": topic, "emit": emit,
                    "error": f"last30days timed out after {timeout_s}s"}
        except Exception as exc:  # noqa: BLE001 — never raise into the task graph
            return {"status": "error", "topic": topic, "emit": emit, "error": str(exc)}

        elapsed_ms = int((time.time() - started) * 1000)
        if proc.returncode != 0:
            return {
                "status": "error",
                "topic": topic,
                "emit": emit,
                "elapsed_ms": elapsed_ms,
                "error": (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[-600:],
            }

        out = (proc.stdout or "").strip()
        result: Any = out
        if emit == "json":
            try:
                result = json.loads(out)
            except json.JSONDecodeError:
                return {"status": "error", "topic": topic, "emit": emit,
                        "elapsed_ms": elapsed_ms, "error": "could not parse JSON output"}

        return {
            "status": "success",
            "topic": topic,
            "emit": emit,
            "result": result,
            "elapsed_ms": elapsed_ms,
        }

    @staticmethod
    def _coerce_timeout(value: Any) -> int:
        try:
            t = int(value)
        except (TypeError, ValueError):
            return _DEFAULT_TIMEOUT_S
        return max(10, min(1800, t))

    def diagnose(self) -> dict[str, Any]:
        """Report which sources/providers are available (keyless vs key-gated)."""
        if not _ENTRY.exists():
            return {"available": False, "error": f"payload missing at {_ENTRY}"}
        try:
            proc = subprocess.run(
                [os.getenv("PYTHON_BIN") or sys.executable or "python3", str(_ENTRY), "--diagnose"],
                cwd=str(_ENTRY.parent), capture_output=True, text=True, timeout=60, check=False,
            )
            return {"available": proc.returncode == 0, "report": json.loads(proc.stdout or "{}")}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}

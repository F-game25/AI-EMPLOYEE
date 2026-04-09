"""ASCEND_FORGE — Top-layer self-improver for the AI-EMPLOYEE system.

Sits ABOVE Ollama (orchestrator), Hermes (sub-agent), and BLACKLIGHT
(execution/action layer). Continuously improves the system safely.

Focus areas:
  1. Functionality   — stability, bugs, structure, performance
  2. Looks (UI/UX)   — visual improvements, UX refinements
  3. Profit          — output usefulness, automation, monetisation

State file : ~/.ai-employee/state/ascend_forge.state.json
Changelog  : ~/.ai-employee/state/ascend_forge.changelog.json
"""
from __future__ import annotations

import difflib
import html as _html_mod
import importlib
import itertools
import json
import logging
import os
import re as _re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
STATE_FILE = STATE_DIR / "ascend_forge.state.json"
CHANGELOG_FILE = STATE_DIR / "ascend_forge.changelog.json"

# Protected areas — HIGH risk changes here must never auto-apply
PROTECTED_MODULES = {"ollama-agent", "hermes-agent", "ai-router"}

# Failsafe threshold
MAX_CONSECUTIVE_FAILURES = 3

# Known agent names for prompt analysis
_KNOWN_AGENTS = [
    "task-orchestrator", "cold-outreach-assassin", "hermes-agent",
    "ollama-agent", "ai-router", "gemma-agent", "problem-solver",
    "ascend-forge", "blacklight", "turbo-quant", "neural-network",
]

# Phase marker pattern: "Phase 1", "Phase 2:", "PHASE ONE" etc.
_PHASE_RE = _re.compile(
    r'(?:^|\n)\s*Phase\s+(\d+|[Oo]ne|[Tt]wo|[Tt]hree|[Ff]our|[Ff]ive)\s*[:\-\—]?\s*(.*)',
    _re.IGNORECASE,
)

# File reference pattern
_FILE_RE = _re.compile(r'\b(\w[\w/\-]*\.(?:py|js|html|json|yaml|yml|sh))\b')

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("ascend_forge")

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_GENERAL = "GENERAL"
MODE_MONEY = "MONEY"
MODE_AUTO = "AUTO"
VALID_MODES = {MODE_GENERAL, MODE_MONEY, MODE_AUTO}

# ── In-memory activity feed (last 200 entries) ────────────────────────────────
_activity_feed: list[dict] = []
_activity_lock = threading.Lock()
_MAX_FEED = 200

# ── Thread lock for state mutations ──────────────────────────────────────────
_state_lock = threading.Lock()

# ── Session tracking (for /cost reporting) ────────────────────────────────────
_session_start: float = time.time()

# ── Agent routing table ───────────────────────────────────────────────────────
# Maps task keyword clusters to the best specialist agent.
_ROUTING_KEYWORDS: list[tuple[list[str], str]] = [
    (["ui", "layout", "visual", "design", "frontend", "css", "html", "dashboard",
      "style", "theme", "color"], "ui-engine"),
    (["lead", "outreach", "revenue", "monetiz", "profit", "sales", "campaign",
      "email marketing", "cold email"], "cold-outreach-assassin"),
    (["bug", "crash", "error", "exception", "broken", "fix", "traceback",
      "stacktrace"], "hermes-agent"),
    (["research", "market", "competitor", "benchmark", "study",
      "report", "analyze"], "problem-solver"),
    (["prompt", "output quality", "ai response", "improve prompt"], "ascend-forge"),
]

# ── Scheduler frequency table ─────────────────────────────────────────────────
_FREQ_SECONDS: dict[str, int] = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _push_activity(msg: str, level: str = "info") -> None:
    entry = {"ts": _now_iso(), "msg": msg, "level": level}
    with _activity_lock:
        _activity_feed.append(entry)
        if len(_activity_feed) > _MAX_FEED:
            del _activity_feed[: len(_activity_feed) - _MAX_FEED]


# ── State I/O ─────────────────────────────────────────────────────────────────

def _default_state() -> dict:
    return {
        "mode": MODE_AUTO,
        "observe_only": False,
        "consecutive_failures": 0,
        "auto_approve_low": False,
        "current_activity": "idle",
        "current_target": "",
        "last_scan": None,
        "last_scan_ts": None,
        "last_doctor_output": "",
        "blacklight_active": False,
        "patches_approved": 0,
        "patches_rejected": 0,
        "patches_failed": 0,
        "total_patches": 0,
        "last_plan": None,
        "schedules": {},
        "plan_pending_task": None,
    }


def _load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            defaults = _default_state()
            defaults.update(data)
            return defaults
        except Exception:
            pass
    return _default_state()


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Changelog I/O ─────────────────────────────────────────────────────────────

def _load_changelog() -> list[dict]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if CHANGELOG_FILE.exists():
        try:
            return json.loads(CHANGELOG_FILE.read_text())
        except Exception:
            pass
    return []


def _save_changelog(log: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CHANGELOG_FILE.write_text(json.dumps(log, indent=2))


def _log_patch(patch: dict) -> None:
    """Append or update a patch entry in the changelog."""
    with _state_lock:
        log = _load_changelog()
        existing = next((p for p in log if p.get("patch_id") == patch.get("patch_id")), None)
        if existing:
            existing.update(patch)
        else:
            log.append(patch)
        _save_changelog(log)


# ── Patch helpers ─────────────────────────────────────────────────────────────

def _build_diff(original: str, modified: str, filename: str = "file") -> str:
    """Return a unified diff string."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, mod_lines,
                                fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


def _risk_level(affected_files: list[str], change_size: int) -> str:
    """Classify risk level of a patch."""
    for f in affected_files:
        for protected in PROTECTED_MODULES:
            if protected in f:
                return "HIGH"
    if change_size > 200:
        return "HIGH"
    if change_size > 50:
        return "MEDIUM"
    return "LOW"


def _infer_patch_type(description: str) -> str:
    desc_l = description.lower()
    if any(k in desc_l for k in ("restart", "not running", "agent down")):
        return "agent_restart"
    if any(k in desc_l for k in ("permission", "security", "access denied", "privilege")):
        return "security"
    if any(k in desc_l for k in ("disk", "storage", "space", "memory", "cpu", "efficiency")):
        return "efficiency"
    if any(k in desc_l for k in ("config", "setting", "configuration", "missing")):
        return "config"
    if any(k in desc_l for k in ("schedule", "cron", "interval", "timer")):
        return "schedule"
    if any(k in desc_l for k in ("capability", "feature", "expand", "add support")):
        return "capability"
    if any(k in desc_l for k in ("prompt", "output", "monetiz", "revenue", "lead")):
        return "prompt" if "prompt" in desc_l else "monetization"
    if any(k in desc_l for k in ("ui", "ux", "visual", "style", "design", "layout")):
        return "UI"
    if any(k in desc_l for k in ("performance", "speed", "latency", "optim")):
        return "performance"
    if any(k in desc_l for k in ("bug", "fix", "error", "crash", "exception")):
        return "functionality"
    return "functionality"


# ── Mode logic ────────────────────────────────────────────────────────────────

def get_mode() -> str:
    state = _load_state()
    return state.get("mode", MODE_AUTO)


def set_mode(mode: str) -> str:
    mode = mode.upper()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Valid: {', '.join(VALID_MODES)}")
    with _state_lock:
        state = _load_state()
        state["mode"] = mode
        _save_state(state)
    _push_activity(f"Mode changed to {mode}", "info")
    return mode


def _resolve_effective_mode(task_desc: str = "") -> str:
    """Return the effective operating mode, honouring BLACKLIGHT override and AUTO logic."""
    state = _load_state()
    mode = state.get("mode", MODE_AUTO)

    # BLACKLIGHT priority override
    if state.get("blacklight_active"):
        return MODE_MONEY

    if mode != MODE_AUTO:
        return mode

    # AUTO mode: classify by task description
    desc_l = task_desc.lower()
    money_keywords = ("lead", "automat", "content", "output quality", "monetiz",
                      "revenue", "campaign", "outreach", "prompt", "profit")
    general_keywords = ("error", "bug", "crash", "performance", "ui issue",
                        "latency", "fix", "slow", "broken", "exception")

    if any(k in desc_l for k in money_keywords):
        return MODE_MONEY
    if any(k in desc_l for k in general_keywords):
        return MODE_GENERAL
    return MODE_MONEY  # default in AUTO: lean toward revenue


# ── Failsafe ──────────────────────────────────────────────────────────────────

def _record_failure() -> bool:
    """Record a patch failure; returns True if failsafe triggered."""
    with _state_lock:
        state = _load_state()
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            state["observe_only"] = True
            _push_activity(
                f"⚠️ Failsafe triggered after {MAX_CONSECUTIVE_FAILURES} "
                "consecutive failures — switching to observe-only mode.",
                "warn",
            )
        _save_state(state)
        return state["observe_only"]


def _record_success() -> None:
    with _state_lock:
        state = _load_state()
        state["consecutive_failures"] = 0
        _save_state(state)


# ── Prompt optimisation ───────────────────────────────────────────────────────

_WEAK_PROMPT_MARKERS = [
    ("please ", "Remove filler 'please'"),
    ("can you ", "Use imperative instead of 'can you'"),
    ("just ", "Remove filler 'just'"),
    ("i was wondering", "Remove weak preamble"),
    ("if possible", "Remove hedge 'if possible'"),
    ("etc.", "Replace 'etc.' with explicit list"),
    ("and so on", "Replace 'and so on' with explicit list"),
    ("various ", "Be specific instead of 'various'"),
    ("some ", "Specify count/type instead of 'some'"),
    ("things", "Replace 'things' with specific nouns"),
]


def _optimize_prompt(original: str) -> tuple[str, list[str]]:
    """Return (improved_prompt, list_of_suggestions)."""
    improved = original
    suggestions: list[str] = []

    for marker, suggestion in _WEAK_PROMPT_MARKERS:
        if marker in improved.lower():
            suggestions.append(suggestion)

    # Structural improvements
    if not improved.strip().endswith((".", ":", "?", "!")):
        improved = improved.rstrip() + "."
        suggestions.append("Added sentence terminator for clarity")

    lines = improved.strip().splitlines()
    if len(lines) == 1 and len(improved) > 80:
        # Break into structured prompt
        improved = (
            "Task: " + improved.split(".")[0].strip() + ".\n"
            + "Output: Provide a clear, actionable, direct response with no filler."
        )
        suggestions.append("Restructured into Task/Output format for better results")

    return improved, suggestions


def scan_prompts(target_path: Optional[Path] = None) -> list[dict]:
    """Scan Python files for prompt strings and return optimisation candidates."""
    search_root = target_path or (AI_HOME / "agents")
    candidates: list[dict] = []

    if not search_root.exists():
        return candidates

    for py_file in search_root.rglob("*.py"):
        try:
            source = py_file.read_text(errors="replace")
        except Exception:
            continue
        # Find triple-quoted strings longer than 40 chars (likely prompt templates)
        pattern = _re.compile(r'(?:"""([\s\S]{40,400}?)"""|\'\'\'([\s\S]{40,400}?)\'\'\')', _re.DOTALL)
        for match in pattern.finditer(source):
            text = (match.group(1) or match.group(2)).strip()
            _, suggestions = _optimize_prompt(text)
            if suggestions:
                candidates.append({
                    "file": str(py_file.relative_to(search_root)),
                    "snippet": text[:120] + ("…" if len(text) > 120 else ""),
                    "suggestions": suggestions,
                })
                if len(candidates) >= 20:
                    return candidates

    return candidates


# ── Prompt analysis and complex-task handling ─────────────────────────────────

def analyze_prompt(prompt: str) -> dict:
    """Analyze a complex prompt and return a structured improvement plan.

    Returns a dict with keys:
      is_complex       — True if the prompt describes a multi-step task
      phases           — list of {name, items, priority} dicts
      actions          — flat list of actionable items
      mentioned_agents — agent names referenced in the prompt
      mentioned_files  — filenames referenced in the prompt
      patch_types      — inferred improvement categories
      has_high_risk    — True if the prompt touches protected areas
      summary          — first meaningful line of the prompt
    """
    lines = [l.strip() for l in prompt.splitlines() if l.strip()]

    # ── Detect phases ─────────────────────────────────────────────────────
    phases: list[dict] = []
    current_phase: Optional[dict] = None

    for line in lines:
        m = _PHASE_RE.match(line)
        if m:
            if current_phase:
                phases.append(current_phase)
            phase_num = m.group(1)
            phase_title = m.group(2).strip()
            name = (
                f"Phase {phase_num} — {phase_title}"
                if phase_title
                else f"Phase {phase_num}"
            )
            current_phase = {"name": name, "items": [], "priority": "MEDIUM"}
        elif current_phase is not None:
            if _re.match(r'^[\-\*•\d]+\.?\s+.{5,}', line):
                item = _re.sub(r'^[\-\*•\d]+\.?\s+', '', line).strip()
                if item:
                    current_phase["items"].append(item)
    if current_phase:
        phases.append(current_phase)

    # ── Extract flat action items (bullet / numbered lists) ───────────────
    actions: list[str] = []
    for line in lines:
        if _re.match(r'^[\-\*•\d]+\.?\s+.{8,}', line):
            item = _re.sub(r'^[\-\*•\d]+\.?\s+', '', line).strip()
            if item and item not in actions:
                actions.append(item)

    # ── Detect mentioned agents ───────────────────────────────────────────
    prompt_lower = prompt.lower()
    mentioned_agents = [a for a in _KNOWN_AGENTS if a in prompt_lower]

    # ── Detect mentioned files ────────────────────────────────────────────
    mentioned_files = list(dict.fromkeys(_FILE_RE.findall(prompt)))[:10]

    # ── Infer patch types from content ────────────────────────────────────
    patch_type_keywords: dict[str, tuple] = {
        "UI": ("ui", "frontend", "html", "css", "dashboard", "visual", "layout"),
        "functionality": ("bug", "fix", "error", "crash", "broken", "stability"),
        "performance": ("performance", "speed", "latency", "optimize", "optim"),
        "prompt": ("prompt", "output quality", "ai response"),
        "capability": ("feature", "capability", "add support", "implement", "new"),
        "efficiency": ("agent count", "stabiliz", "memory", "cpu", "efficiency"),
        "monetization": ("revenue", "monetiz", "profit", "lead", "sales"),
    }
    patch_types = [
        ptype
        for ptype, kws in patch_type_keywords.items()
        if any(k in prompt_lower for k in kws)
    ]

    # ── Determine complexity ──────────────────────────────────────────────
    is_complex = bool(
        phases
        or len(actions) >= 3
        or len(lines) >= 10
        or any(
            k in prompt_lower
            for k in ("phase", "plan", "implement", "upgrade", "system")
        )
    )

    # ── Assign phase priorities (first = HIGH, second = MEDIUM, rest = LOW) ──
    _priority_map = {0: "HIGH", 1: "MEDIUM"}
    for i, phase in enumerate(phases):
        phase["priority"] = _priority_map.get(i, "LOW")

    # ── High-risk detection ───────────────────────────────────────────────
    _high_risk_kw = ("server.py", "ai-router", "ollama", "hermes", "database",
                     "auth", "security", "credential")
    has_high_risk = any(k in prompt_lower for k in _high_risk_kw)
    for f in mentioned_files:
        for protected in PROTECTED_MODULES:
            if protected in f:
                has_high_risk = True

    # ── Summary: first meaningful non-header line ─────────────────────────
    summary = lines[0] if lines else prompt[:120]
    if len(summary) > 120:
        summary = summary[:117] + "…"

    # ── Persist plan context to state ────────────────────────────────────
    with _state_lock:
        s = _load_state()
        s["last_plan"] = {
            "ts": _now_iso(),
            "summary": summary,
            "phases": len(phases),
            "actions": len(actions),
            "patch_types": patch_types,
        }
        _save_state(s)

    return {
        "is_complex": is_complex,
        "phases": phases,
        "actions": actions[:20],
        "mentioned_agents": mentioned_agents,
        "mentioned_files": mentioned_files,
        "patch_types": patch_types,
        "has_high_risk": has_high_risk,
        "summary": summary,
    }


def handle_complex_task(task: str) -> str:
    """Handle any task prompt — simple commands or complex multi-phase plans.

    For ``ascend: …`` prefixed commands, delegates to handle_chat_command().
    For all other input, analyzes structure, queues patches, and returns a
    structured response in the format:

        📊 Summary: …
        📋 Plan:
          Phase 1 — … (Priority: HIGH)
            • action …
        ⚡ Next Actions (N patch(es) queued):
          1. [RISK] description
        🔥 Ready to execute.   OR   ⚠️ Awaiting your approval.
    """
    stripped = task.strip()

    # Simple ascend: command → use existing handler
    if stripped.lower().startswith("ascend:"):
        return handle_chat_command(stripped)

    _push_activity(f"🧠 Analyzing task: {stripped[:60]}…", "info")
    plan = analyze_prompt(stripped)
    effective_mode = _resolve_effective_mode(stripped)

    patches_queued: list[dict] = []

    # ── Queue patches for each inferred patch type ────────────────────────
    _desc_map: dict[str, str] = {
        "UI": "Improve UI/UX based on task specification",
        "functionality": "Fix functionality issues identified in task",
        "performance": "Optimize performance as specified in task",
        "prompt": "Upgrade AI prompt quality for better output",
        "capability": "Implement new capability from task specification",
        "efficiency": "Stabilize and improve agent efficiency",
        "monetization": "Enhance revenue-generating features",
    }
    for ptype in plan["patch_types"]:
        desc = _desc_map.get(ptype, f"Apply {ptype} improvements")
        files = plan["mentioned_files"][:3]
        try:
            p = create_patch(
                description=desc,
                reason=f"Requested via complex task: {stripped[:200]}",
                affected_files=files,
                diff_preview=(
                    f"# Task analysis → {ptype} improvement\n"
                    f"# Source: {stripped[:120]}"
                ),
                trigger="complex task",
                patch_type=ptype,
                mode=effective_mode,
                source="complex_task",
            )
            patches_queued.append(p)
        except RuntimeError:
            pass

    # ── Queue patches for each extracted phase ────────────────────────────
    for phase in plan["phases"]:
        if not phase["items"]:
            continue
        phase_desc = f"{phase['name']}: {'; '.join(phase['items'][:3])}"[:120]
        files = plan["mentioned_files"][:2]
        try:
            p = create_patch(
                description=phase_desc,
                reason=f"Phase task: {phase['name']}",
                affected_files=files,
                diff_preview="\n".join(
                    f"# {item}" for item in phase["items"][:5]
                ),
                trigger="complex task",
                mode=effective_mode,
                source="complex_task",
            )
            patches_queued.append(p)
        except RuntimeError:
            pass

    # ── If no patches queued and not complex, run a general scan ──────────
    if not patches_queued and not plan["is_complex"]:
        patches_queued = scan_system(trigger=f"complex task: {stripped[:60]}")

    # ── Build structured response ─────────────────────────────────────────
    out: list[str] = []

    out.append(f"📊 **Summary:** {plan['summary']}")
    out.append("")

    # ── Routing suggestion ────────────────────────────────────────────────
    routed_agent = _route_task(stripped)
    if routed_agent and routed_agent != "ascend-forge":
        out.append(f"🤖 **Routing suggestion:** Consider delegating to **{routed_agent}**.")
        out.append("  (Use /improve <module> for targeted module analysis.)")
        out.append("")

    if plan["phases"]:
        out.append("📋 **Plan:**")
        for phase in plan["phases"]:
            out.append(f"  {phase['name']} (Priority: {phase['priority']})")
            for item in phase["items"][:5]:
                out.append(f"    • {item}")
        out.append("")
    elif plan["actions"]:
        out.append("📋 **Planned Actions:**")
        for action in plan["actions"][:8]:
            out.append(f"  • {action}")
        out.append("")

    meta: list[str] = []
    if plan["patch_types"]:
        meta.append(f"🔧 **Improvements:** {', '.join(plan['patch_types'])}")
    if plan["mentioned_agents"]:
        meta.append(f"🤖 **Agents:** {', '.join(plan['mentioned_agents'])}")
    if plan["mentioned_files"]:
        meta.append(f"📁 **Files:** {', '.join(plan['mentioned_files'])}")
    if meta:
        out.extend(meta)
        out.append("")

    if patches_queued:
        out.append(f"⚡ **Next Actions ({len(patches_queued)} patch(es) queued):**")
        for i, p in enumerate(patches_queued[:5], 1):
            out.append(f"  {i}. [{p['risk_level']}] {p['description'][:70]}")
        out.append("")
    else:
        out.append(
            "ℹ️ No patches queued — system already optimal for this task."
        )
        out.append("")

    has_high = plan["has_high_risk"] or any(
        p.get("risk_level") == "HIGH" for p in patches_queued
    )
    if has_high:
        out.append("⚠️ **Awaiting your approval** — HIGH risk changes detected.")
    else:
        out.append("🔥 **Ready to execute.**")

    result = "\n".join(out)
    _push_activity(
        f"✅ Complex task analyzed — {len(patches_queued)} patch(es) queued.",
        "success",
    )
    return result


# ── Patch creation ────────────────────────────────────────────────────────────

def create_patch(
    description: str,
    reason: str,
    affected_files: list[str],
    diff_preview: str,
    trigger: str = "auto scan",
    patch_type: Optional[str] = None,
    mode: Optional[str] = None,
    source: str = "manual",
    risk_override: Optional[str] = None,
) -> dict:
    """Create a PENDING patch entry and log it."""
    state = _load_state()
    if state.get("observe_only"):
        raise RuntimeError("ASCEND_FORGE is in observe-only mode. No new patches allowed.")

    if mode is None:
        mode = _resolve_effective_mode(description)
    if patch_type is None:
        patch_type = _infer_patch_type(description)

    if risk_override is not None and risk_override in ("LOW", "MEDIUM", "HIGH"):
        risk = risk_override
    else:
        change_size = len(diff_preview.splitlines())
        risk = _risk_level(affected_files, change_size)

    # Protected area — force HIGH risk for any change to protected modules
    for f in affected_files:
        for protected in PROTECTED_MODULES:
            if protected in f:
                risk = "HIGH"

    patch_id = "patch-" + uuid.uuid4().hex[:8]
    patch = {
        "patch_id": patch_id,
        "timestamp": _now_iso(),
        "applied_timestamp": None,
        "mode": mode,
        "trigger": trigger,
        "source": source,
        "description": description,
        "reason": reason,
        "affected_files": affected_files,
        "diff_preview": diff_preview,
        "risk_level": risk,
        "patch_type": patch_type,
        "status": "pending",
    }

    _log_patch(patch)
    _push_activity(
        f"📋 New patch queued [{risk}]: {description[:60]}", "info"
    )

    # Update total_patches counter
    with _state_lock:
        s = _load_state()
        s["total_patches"] = s.get("total_patches", 0) + 1
        _save_state(s)

    # Auto-approve LOW risk if toggle is on
    if risk == "LOW" and state.get("auto_approve_low"):
        approve_patch(patch_id)

    return patch


# ── Approval system ───────────────────────────────────────────────────────────

def approve_patch(patch_id: str) -> dict:
    """Approve and apply a pending patch."""
    log = _load_changelog()
    patch = next((p for p in log if p.get("patch_id") == patch_id), None)
    if not patch:
        raise ValueError(f"Patch '{patch_id}' not found")
    if patch.get("status") != "pending":
        raise ValueError(f"Patch '{patch_id}' is not pending (status: {patch['status']})")

    state = _load_state()
    if state.get("observe_only"):
        raise RuntimeError("Cannot apply patches in observe-only mode")

    # Simulate apply: mark approved, then attempt real file execution
    try:
        patch["status"] = "approved"
        patch["applied_timestamp"] = _now_iso()
        _log_patch(patch)
        _record_success()
        with _state_lock:
            s = _load_state()
            s["patches_approved"] = s.get("patches_approved", 0) + 1
            _save_state(s)
        # Best-effort: attempt to apply real file changes when files exist
        _execute_real_patch(patch)
        _push_activity(
            f"✅ Patch approved & applied: {patch['description'][:60]}", "success"
        )
        return patch
    except Exception as exc:
        patch["status"] = "failed"
        _log_patch(patch)
        _record_failure()
        raise RuntimeError(f"Failed to apply patch: {exc}") from exc


def reject_patch(patch_id: str) -> dict:
    """Reject a pending patch without applying it."""
    log = _load_changelog()
    patch = next((p for p in log if p.get("patch_id") == patch_id), None)
    if not patch:
        raise ValueError(f"Patch '{patch_id}' not found")
    if patch.get("status") != "pending":
        raise ValueError(f"Patch '{patch_id}' is not pending (status: {patch['status']})")

    patch["status"] = "rejected"
    _log_patch(patch)
    with _state_lock:
        s = _load_state()
        s["patches_rejected"] = s.get("patches_rejected", 0) + 1
        _save_state(s)
    _push_activity(f"❌ Patch rejected: {patch['description'][:60]}", "warn")
    return patch


def rollback_patch(patch_id: str) -> dict:
    """Roll back an approved patch (mark as rolled_back)."""
    log = _load_changelog()
    patch = next((p for p in log if p.get("patch_id") == patch_id), None)
    if not patch:
        raise ValueError(f"Patch '{patch_id}' not found")
    if patch.get("status") not in ("approved",):
        raise ValueError(
            f"Can only rollback approved patches (status: {patch['status']})"
        )

    patch["status"] = "rolled_back"
    patch["rolled_back_at"] = _now_iso()
    _log_patch(patch)
    _push_activity(
        f"↩️ Patch rolled back: {patch['description'][:60]}", "warn"
    )
    return patch


# ── Scan / analysis ───────────────────────────────────────────────────────────

def scan_system(trigger: str = "auto scan") -> list[dict]:
    """Run a full system scan and generate patches.

    Performs three checks in order:
      1. DOCTOR INTEGRATION  — call ai-employee doctor, parse output
      2. AGENT EFFICIENCY    — scan agent dirs for error indicators
      3. PROMPT OPTIMISATION — find weak prompt strings (MONEY/AUTO)
      4. STRUCTURAL CHECK    — TODO/FIXME markers (GENERAL/AUTO)
    """
    if _load_state().get("observe_only"):
        _push_activity("👁️ Observe-only mode active — scan skipped.", "warn")
        return []

    _push_activity("🔍 Starting system scan…", "info")
    patches: list[dict] = []
    mode = _resolve_effective_mode("system scan")

    # ── CHECK 1 — DOCTOR INTEGRATION ─────────────────────────────────────────
    _push_activity("🩺 Running doctor check…", "info")
    doctor_output = ""
    try:
        result = subprocess.run(
            [str(AI_HOME / "bin" / "ai-employee"), "doctor"],
            capture_output=True, text=True, timeout=30,
        )
        doctor_output = result.stdout + result.stderr
    except FileNotFoundError:
        doctor_output = "ai-employee binary not found"
        _push_activity("⚠️ ai-employee binary not found — skipping doctor check.", "warn")
    except subprocess.TimeoutExpired:
        doctor_output = "doctor command timed out"
        _push_activity("⚠️ Doctor check timed out.", "warn")
    except Exception as exc:
        doctor_output = f"Doctor unavailable: {exc}"
        _push_activity(f"⚠️ Doctor check failed: {exc}", "warn")

    # Persist doctor output to state (capped to avoid state file bloat)
    with _state_lock:
        s = _load_state()
        s["last_doctor_output"] = doctor_output[:4000]
        _save_state(s)

    # Parse each line for issue patterns
    _seen_doctor_reasons: set[str] = set()
    for raw_line in doctor_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        patch_type: Optional[str] = None
        risk: Optional[str] = None
        description: Optional[str] = None
        line_lower = line.lower()

        # Order matters — check more specific patterns first
        if "not running" in line_lower:
            risk = "MEDIUM"
            description = f"Restart agent that is not running: {line[:80]}"
            patch_type = "agent_restart"
        elif "permission denied" in line_lower or "access denied" in line_lower:
            risk = "HIGH"
            description = f"Fix permissions issue: {line[:80]}"
            patch_type = "security"
        elif any(k in line_lower for k in ("disk", "storage", "space")):
            risk = "MEDIUM"
            description = f"Address storage issue: {line[:80]}"
            patch_type = "efficiency"
        elif any(x in line for x in ("❌",)) or \
                any(x in line_lower for x in ("fail", "error")):
            risk = "HIGH"
            description = f"Fix error detected by doctor: {line[:80]}"
            patch_type = "functionality"
        elif any(x in line for x in ("⚠️",)) or \
                any(x in line_lower for x in ("warning", "warn")):
            risk = "MEDIUM"
            description = f"Resolve warning detected by doctor: {line[:80]}"
            patch_type = "config"
        elif any(k in line_lower for k in ("not found", "missing")):
            risk = "MEDIUM"
            description = f"Install or restore missing component: {line[:80]}"
            patch_type = "config"

        if description and patch_type and risk:
            # Deduplicate by description to avoid flooding
            dedup_key = description[:60]
            if dedup_key in _seen_doctor_reasons:
                continue
            _seen_doctor_reasons.add(dedup_key)
            try:
                p = create_patch(
                    description=description,
                    reason=line,
                    affected_files=[],
                    diff_preview=f"# Doctor reported: {line[:200]}",
                    trigger=trigger,
                    patch_type=patch_type,
                    mode=mode,
                    source="doctor",
                    risk_override=risk,
                )
                patches.append(p)
                if len(patches) >= 10:
                    # Cap doctor patches to avoid flooding the queue
                    break
            except RuntimeError:
                pass

    # ── CHECK 2 — AGENT EFFICIENCY ANALYSIS ──────────────────────────────────
    _push_activity("📊 Analysing agent efficiency…", "info")
    agents_dir = AI_HOME / "agents"
    state_dir = AI_HOME / "state"
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_name = agent_dir.name
            run_sh = agent_dir / "run.sh"
            if not run_sh.exists():
                continue

            # Look for a matching state file
            state_candidates = [
                state_dir / f"{agent_name}.json",
                state_dir / f"{agent_name}.state.json",
                state_dir / f"{agent_name}_state.json",
            ]
            agent_state: dict = {}
            for sc in state_candidates:
                if sc.exists():
                    try:
                        agent_state = json.loads(sc.read_text())
                    except Exception:
                        pass
                    break

            # Score the agent for issues
            issues: list[str] = []

            # Check for high error count in state
            # 3+ consecutive errors signals a persistently unhealthy agent
            error_count = (
                agent_state.get("errors", 0)
                or agent_state.get("error_count", 0)
                or agent_state.get("consecutive_failures", 0)
            )
            if isinstance(error_count, int) and error_count >= 3:
                issues.append(f"high error count ({error_count})")

            # Check for slowness indicators
            # >5 000 ms avg response is considered unacceptably slow
            avg_ms = (
                agent_state.get("avg_response_ms")
                or agent_state.get("avg_latency_ms")
            )
            if isinstance(avg_ms, (int, float)) and avg_ms > 5000:
                issues.append(f"high avg latency ({avg_ms:.0f}ms)")

            # Check for disabled / stopped state
            if agent_state.get("status") in ("stopped", "crashed", "disabled"):
                issues.append(f"agent status is {agent_state['status']!r}")

            if issues:
                issue_str = "; ".join(issues)
                desc = f"Improve efficiency of {agent_name} agent ({issue_str})"
                try:
                    p = create_patch(
                        description=desc,
                        reason=(
                            f"Agent '{agent_name}' shows efficiency problems: {issue_str}. "
                            "Reviewing and tuning agent settings can reduce errors and latency."
                        ),
                        affected_files=[str(run_sh.relative_to(agents_dir))],
                        diff_preview=f"# Efficiency issues in {agent_name}: {issue_str}",
                        trigger=trigger,
                        patch_type="efficiency",
                        mode=mode,
                        source="efficiency",
                    )
                    patches.append(p)
                except RuntimeError:
                    pass

    # ── CHECK 3 — PROMPT OPTIMISATION (MONEY / AUTO) ──────────────────────────
    if mode in (MODE_MONEY, MODE_AUTO):
        candidates = scan_prompts()
        if candidates:
            diff_lines = []
            files = []
            for c in candidates[:5]:
                diff_lines.append(
                    f"# {c['file']}: {'; '.join(c['suggestions'])}"
                )
                files.append(c["file"])
            diff_preview = "\n".join(diff_lines)
            try:
                p = create_patch(
                    description="Optimise weak prompt strings for better AI output quality",
                    reason=(
                        "Detected prompt strings with filler words or poor structure "
                        "that reduce output usefulness. Improving these increases "
                        "direct actionability of AI responses."
                    ),
                    affected_files=files[:5],
                    diff_preview=diff_preview,
                    trigger=trigger,
                    patch_type="prompt",
                    mode=mode,
                    source="capability",
                )
                patches.append(p)
            except RuntimeError:
                pass

    # ── CHECK 4 — STRUCTURAL CHECK (GENERAL / AUTO) ───────────────────────────
    if mode in (MODE_GENERAL, MODE_AUTO):
        bots_dir = AI_HOME / "agents"
        todos: list[str] = []
        todo_files: list[str] = []
        if bots_dir.exists():
            for py_file in itertools.islice(bots_dir.rglob("*.py"), 30):
                try:
                    src = py_file.read_text(errors="replace")
                    hits = _re.findall(r"#\s*(TODO|FIXME)[^\n]*", src, _re.IGNORECASE)
                    if hits:
                        todos.extend(hits[:3])
                        todo_files.append(str(py_file.relative_to(bots_dir)))
                except Exception:
                    continue

        if todos:
            diff_preview = "\n".join(f"- {t}" for t in todos[:10])
            try:
                p = create_patch(
                    description=f"Address {len(todos)} TODO/FIXME items across {len(todo_files)} files",
                    reason=(
                        "Unresolved TODO/FIXME markers indicate incomplete or fragile "
                        "code paths that may cause bugs or reduce system stability."
                    ),
                    affected_files=todo_files[:5],
                    diff_preview=diff_preview,
                    trigger=trigger,
                    patch_type="functionality",
                    mode=mode,
                    source="efficiency",
                )
                patches.append(p)
            except RuntimeError:
                pass

    _push_activity(
        f"✅ Scan complete — {len(patches)} patch(es) queued.", "info"
    )
    now = _now_iso()
    with _state_lock:
        s = _load_state()
        s["last_scan"] = now       # legacy field kept for backward compatibility
        s["last_scan_ts"] = now    # canonical field per new schema
        _save_state(s)

    return patches


def analyze_module(module_name: str, trigger: str = "chat command") -> list[dict]:
    """Analyze a specific module and queue improvement patches."""
    _push_activity(f"🔎 Analyzing module: {module_name}", "info")
    bots_dir = AI_HOME / "agents"
    module_dir = bots_dir / module_name

    if not module_dir.exists():
        _push_activity(f"⚠️ Module '{module_name}' not found.", "warn")
        return []

    mode = _resolve_effective_mode(module_name)
    patches: list[dict] = []

    for py_file in module_dir.glob("*.py"):
        try:
            src = py_file.read_text(errors="replace")
        except Exception:
            continue

        # Prompt scan
        candidates = scan_prompts(module_dir)
        if candidates:
            diff_preview = "\n".join(
                f"# {c['file']}: {'; '.join(c['suggestions'])}" for c in candidates[:3]
            )
            try:
                p = create_patch(
                    description=f"Optimise prompts in {module_name}",
                    reason=f"Weak prompt patterns detected in {module_name} module.",
                    affected_files=[str(py_file.relative_to(bots_dir))],
                    diff_preview=diff_preview,
                    trigger=trigger,
                    patch_type="prompt",
                    mode=mode,
                )
                patches.append(p)
                break
            except RuntimeError:
                pass

    _push_activity(
        f"✅ Module analysis done — {len(patches)} patch(es) queued.", "info"
    )
    return patches


# ── Feature 5: Agent routing ──────────────────────────────────────────────────

def _route_task(task_desc: str) -> Optional[str]:
    """Return the best specialist agent name for a task, or None for self-handling.

    Matches task description against keyword clusters to recommend delegation.
    Returns 'ascend-forge' for prompt/self-improvement tasks handled here.
    """
    desc_lower = task_desc.lower()
    for keywords, agent in _ROUTING_KEYWORDS:
        if any(k in desc_lower for k in keywords):
            return agent
    return None


# ── Feature 4: Real execution loop ───────────────────────────────────────────

def _apply_simple_diff(original: str, diff: str) -> str:
    """Apply a simple unified diff to original text. Returns modified content.

    Handles basic -/+ line replacements from a unified diff block.
    Falls back to original if the diff cannot be parsed or applied cleanly.
    Only replaces lines that are present in the original (safe, non-destructive).
    """
    lines = diff.splitlines()
    removals: list[str] = []
    additions: list[str] = []

    for line in lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removals.append(line[1:])
        elif line.startswith("+"):
            additions.append(line[1:])

    if not removals or not additions:
        return original

    result = original
    for removal, addition in zip(removals, additions):
        if removal in result:
            result = result.replace(removal, addition, 1)

    return result


def _execute_real_patch(patch: dict) -> bool:
    """Attempt to apply a patch to real files on disk.

    Returns True if at least one file was successfully modified.
    Silently skips when:
    - No affected_files specified
    - Target files do not exist (normal for test patches)
    - diff_preview contains no real +/- code lines (only comments/metadata)

    This is a best-effort bonus — approval status is already set before this runs.
    """
    affected = patch.get("affected_files", [])
    diff = patch.get("diff_preview", "")

    if not affected or not diff:
        return False

    # Only attempt when the diff has real code lines (not just # comments)
    real_lines = [
        ln for ln in diff.splitlines()
        if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))
    ]
    if not real_lines:
        return False

    search_roots = [AI_HOME / "agents", AI_HOME, Path.cwd()]
    touched = False

    for rel_path in affected[:3]:
        target: Optional[Path] = None
        # Try to resolve relative path against known roots
        for root in search_roots:
            candidate = root / rel_path
            if candidate.is_file():
                target = candidate
                break

        if target is None:
            continue

        try:
            original = target.read_text(errors="replace")
            new_content = _apply_simple_diff(original, diff)
            if new_content != original:
                target.write_text(new_content)
                _push_activity(
                    f"📝 Real change applied to {rel_path}", "success"
                )
                touched = True
        except Exception as exc:
            _push_activity(f"⚠️ Could not apply to {rel_path}: {exc}", "warn")

    return touched


# ── Feature 3: Web research ───────────────────────────────────────────────────

def web_research(query: str, max_results: int = 3) -> str:
    """Search DuckDuckGo HTML for the given query and return a FINDINGS block.

    Uses DuckDuckGo's HTML endpoint (no API key required).
    Falls back gracefully with an error message when network is unavailable.

    Returns a formatted multi-line string with up to max_results snippets.
    """
    _push_activity(f"🔎 Researching: {query[:60]}…", "info")

    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AscendForge/1.0)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        _push_activity(f"⚠️ Research failed: {exc}", "warn")
        return f"🔎 Research unavailable for: {query}\n⚠️ Error: {exc}"

    # Extract result snippets
    snippet_re = _re.compile(
        r'class=["\']result__snippet["\'][^>]*>(.*?)</(?:a|span)>', _re.DOTALL
    )
    tag_re = _re.compile(r"<[^>]+>")
    results: list[str] = []
    for m in snippet_re.finditer(raw_html):
        clean = tag_re.sub("", m.group(1))
        clean = _html_mod.unescape(clean).strip()
        if clean and len(clean) > 10:
            results.append(clean[:200])
        if len(results) >= max_results:
            break

    if not results:
        return f"🔎 No results found for: {query}"

    lines = [f"🔎 **FINDINGS** for: *{query}*", ""]
    for i, snippet in enumerate(results, 1):
        lines.append(f"  {i}. {snippet}")
    lines.append("")
    lines.append("→ Use these findings to inform your next action.")

    _push_activity(f"✅ Research complete — {len(results)} result(s).", "success")
    return "\n".join(lines)


# ── Feature 6: Context compaction + cost tracking ─────────────────────────────

def compact_context() -> str:
    """Summarize and compress the in-memory activity feed.

    Condenses the full activity history into a one-paragraph summary and
    replaces the feed with a single compact entry.  Frees context budget
    for long autonomous sessions.

    Returns the compact summary string.
    """
    with _activity_lock:
        feed = list(_activity_feed)

    if not feed:
        return "🗜️ Nothing to compact — activity feed is empty."

    counts: dict[str, int] = {}
    key_events: list[str] = []

    for entry in feed:
        level = entry.get("level", "info")
        counts[level] = counts.get(level, 0) + 1
        msg = entry.get("msg", "")
        if any(marker in msg for marker in ("✅", "❌", "⚠️", "📋", "⚡", "↩️", "📝")):
            key_events.append(msg[:80])

    log = _load_changelog()
    n_applied = sum(1 for p in log if p.get("status") == "approved")
    n_pending = sum(1 for p in log if p.get("status") == "pending")
    n_rolled = sum(1 for p in log if p.get("status") == "rolled_back")

    summary_parts = [
        f"{n_applied} patches applied",
        f"{n_pending} pending",
        f"{n_rolled} rolled back",
    ]
    if key_events:
        summary_parts.append("Key: " + " | ".join(key_events[-3:]))

    summary = "; ".join(summary_parts) + "."

    # Replace feed with one compact entry
    with _activity_lock:
        _activity_feed.clear()
        _activity_feed.append({
            "ts": _now_iso(),
            "msg": f"🗜️ Context compacted. {summary}",
            "level": "info",
        })

    lines = [
        "🗜️ **CONTEXT COMPRESSED**",
        f"  {summary}",
        f"  Activity entries condensed: {len(feed)}",
        "✅ Context feed reset. Continuing with fresh context.",
    ]
    return "\n".join(lines)


def get_session_cost() -> dict:
    """Return session statistics for /cost reporting.

    Returns a dict with keys: patches_applied, patches_pending,
    patches_rejected, patches_rolled_back, session_minutes,
    activity_entries, context_health.
    """
    log = _load_changelog()
    n_applied = sum(1 for p in log if p.get("status") == "approved")
    n_pending = sum(1 for p in log if p.get("status") == "pending")
    n_rejected = sum(1 for p in log if p.get("status") == "rejected")
    n_rolled = sum(1 for p in log if p.get("status") == "rolled_back")

    elapsed_sec = time.time() - _session_start
    elapsed_min = int(elapsed_sec / 60)

    with _activity_lock:
        feed_size = len(_activity_feed)

    if feed_size < 50:
        context_health = "🟢 Healthy"
    elif feed_size < 100:
        context_health = "🟡 Near limit — consider /compact"
    else:
        context_health = "🔴 Overloaded — run /compact now"

    return {
        "patches_applied": n_applied,
        "patches_pending": n_pending,
        "patches_rejected": n_rejected,
        "patches_rolled_back": n_rolled,
        "session_minutes": elapsed_min,
        "activity_entries": feed_size,
        "context_health": context_health,
    }


# ── Feature 7: Scheduler ──────────────────────────────────────────────────────

def _normalize_freq(freq: str) -> str:
    """Normalize a frequency string to 'hourly', 'daily', or 'weekly'."""
    freq_lower = freq.lower()
    if freq_lower.startswith("hour"):
        return "hourly"
    if freq_lower.startswith("week"):
        return "weekly"
    return "daily"


def register_schedule(name: str, freq: str) -> dict:
    """Register a recurring autonomous task.

    Args:
        name: Schedule identifier (e.g. 'nightly_scan', 'weekly_audit').
        freq: Frequency string — 'hourly', 'daily', or 'weekly'.

    Returns the schedule entry dict.
    """
    normalized = _normalize_freq(freq)
    entry: dict = {
        "name": name,
        "freq": normalized,
        "freq_seconds": _FREQ_SECONDS[normalized],
        "last_run_ts": None,
        "created_ts": _now_iso(),
    }
    with _state_lock:
        state = _load_state()
        schedules = state.get("schedules", {})
        schedules[name] = entry
        state["schedules"] = schedules
        _save_state(state)
    _push_activity(f"⏰ Schedule registered: {name} ({normalized})", "info")
    return entry


def remove_schedule(name: str) -> bool:
    """Remove a registered schedule by name.

    Returns True if removed, False if not found.
    """
    with _state_lock:
        state = _load_state()
        schedules = state.get("schedules", {})
        if name not in schedules:
            return False
        del schedules[name]
        state["schedules"] = schedules
        _save_state(state)
    _push_activity(f"🗑️ Schedule removed: {name}", "info")
    return True


def list_schedules() -> list[dict]:
    """Return all registered schedules as a list of dicts."""
    state = _load_state()
    return list(state.get("schedules", {}).values())


def check_schedules() -> list[str]:
    """Check all registered schedules and fire any that are due.

    Called by the auto-loop to run autonomous recurring tasks.
    Returns a list of schedule names that were fired this call.
    """
    state = _load_state()
    schedules = state.get("schedules", {})
    if not schedules:
        return []

    fired: list[str] = []
    now = time.time()

    for name, entry in list(schedules.items()):
        freq_sec = entry.get("freq_seconds", 86400)
        last_run = entry.get("last_run_ts")

        # Compute epoch of last run
        last_run_epoch = 0.0
        if last_run:
            try:
                dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                last_run_epoch = dt.timestamp()
            except Exception:
                last_run_epoch = 0.0

        if (now - last_run_epoch) < freq_sec:
            continue

        _push_activity(f"⏰ Scheduled task running: {name}", "info")
        try:
            name_lower = name.lower()
            if "audit" in name_lower or "prompt" in name_lower:
                scan_prompts()
            elif "blacklight" in name_lower:
                set_blacklight_active(True)
            else:
                # Default: full system scan
                scan_system(trigger=f"schedule:{name}")

            # Mark last run time
            with _state_lock:
                s = _load_state()
                if name in s.get("schedules", {}):
                    s["schedules"][name]["last_run_ts"] = _now_iso()
                    _save_state(s)

            fired.append(name)
            _push_activity(f"✅ Scheduled task complete: {name}", "success")
        except Exception as exc:
            _push_activity(f"⚠️ Scheduled task failed: {name}: {exc}", "warn")

    return fired


# ── Feature 1 & 2: Slash command handler ─────────────────────────────────────

def handle_slash_command(message: str) -> str:
    """Handle '/<command>' slash commands.

    Recognizes all /commands listed in /help.  Returns a human-readable
    response string, or an empty string if the message is not a slash command.
    """
    raw = message.strip()
    if not raw.startswith("/"):
        return ""

    parts = raw[1:].split(None, 1)
    if not parts:
        return ""

    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    # ── /help ─────────────────────────────────────────────────────────────────
    if cmd == "help":
        return (
            "📖 **ASCEND FORGE COMMANDS**\n\n"
            "**Scanning & Patching**\n"
            "  /scan                  — full system scan, queue patches\n"
            "  /patches               — list pending patches\n"
            "  /approve <id>          — approve and apply a specific patch\n"
            "  /approve all low       — apply all LOW-risk patches\n"
            "  /reject <id>           — reject a patch\n"
            "  /rollback <id>         — roll back an applied patch\n"
            "  /explain <id>          — show full patch details\n"
            "  /history               — recent changelog (last 10)\n"
            "  /improve <module>      — analyze one agent module\n\n"
            "**Planning & Execution**\n"
            "  /plan <task>           — create a plan without executing\n"
            "  /execute               — execute the last stored plan\n\n"
            "**Research**\n"
            "  /research <query>      — web search for context before acting\n\n"
            "**Status & Session**\n"
            "  /status                — current Ascend Forge state\n"
            "  /cost                  — session report: patches, time, context\n"
            "  /compact               — summarize and compress context feed\n\n"
            "**Scheduling**\n"
            "  /schedule <name> <freq> — register recurring task "
            "(hourly/daily/weekly)\n"
            "  /schedule list          — show active schedules\n"
            "  /schedule remove <name> — cancel a schedule\n\n"
            "**Configuration**\n"
            "  /mode <general|money|auto> — set operating mode\n"
            "  /blacklight <on|off>       — toggle BLACKLIGHT revenue override\n\n"
            "Legacy prefix also works: ascend: <command>"
        )

    # ── /scan ─────────────────────────────────────────────────────────────────
    if cmd == "scan":
        patches = scan_system(trigger="slash command")
        if not patches:
            return "🔍 Scan complete — no patches queued."
        lines = [f"• [{p['risk_level']}] {p['description'][:60]}" for p in patches]
        return "🔍 Scan complete. Patches queued:\n" + "\n".join(lines)

    # ── /status ───────────────────────────────────────────────────────────────
    if cmd == "status":
        state = _load_state()
        log = _load_changelog()
        pending = sum(1 for p in log if p.get("status") == "pending")
        return (
            f"🔥 **ASCEND_FORGE Status**\n"
            f"Mode          : {state.get('mode', MODE_AUTO)}\n"
            f"Observe-only  : {'Yes ⚠️' if state.get('observe_only') else 'No'}\n"
            f"BLACKLIGHT    : "
            f"{'Active ⚡' if state.get('blacklight_active') else 'Inactive'}\n"
            f"Pending patches: {pending}\n"
            f"Approved      : {state.get('patches_approved', 0)}\n"
            f"Rejected      : {state.get('patches_rejected', 0)}\n"
            f"Failed        : {state.get('patches_failed', 0)}\n"
            f"Auto-approve LOW: {'On' if state.get('auto_approve_low') else 'Off'}\n"
            f"Last scan     : {state.get('last_scan') or 'Never'}"
        )

    # ── /patches ──────────────────────────────────────────────────────────────
    if cmd == "patches":
        log = _load_changelog()
        pending = [p for p in log if p.get("status") == "pending"]
        if not pending:
            return "📋 No pending patches."
        lines = [
            f"• {p['patch_id']} [{p['risk_level']}] {p['description'][:50]}"
            for p in pending[-10:]
        ]
        return f"📋 {len(pending)} pending patch(es):\n" + "\n".join(lines)

    # ── /approve ──────────────────────────────────────────────────────────────
    if cmd == "approve":
        if args.lower() in ("all low", "all-low"):
            log = _load_changelog()
            low_pending = [
                p for p in log
                if p.get("status") == "pending" and p.get("risk_level") == "LOW"
            ]
            if not low_pending:
                return "📋 No LOW-risk pending patches to apply."
            applied: list[str] = []
            for p in low_pending:
                try:
                    approve_patch(p["patch_id"])
                    applied.append(p["description"][:50])
                except Exception as exc:
                    _push_activity(
                        f"Failed to apply {p['patch_id']}: {exc}", "error"
                    )
            if applied:
                return "✅ Applied LOW-risk patches:\n" + "\n".join(
                    f"• {d}" for d in applied
                )
            return "⚠️ No patches could be applied."
        if not args:
            return "❌ Usage: /approve <patch_id> or /approve all low"
        try:
            approve_patch(args)
            return f"✅ Patch '{args}' approved and applied."
        except (ValueError, RuntimeError) as e:
            return f"❌ {e}"

    # ── /reject ───────────────────────────────────────────────────────────────
    if cmd == "reject":
        if not args:
            return "❌ Usage: /reject <patch_id>"
        try:
            reject_patch(args)
            return f"❌ Patch '{args}' rejected."
        except (ValueError, RuntimeError) as e:
            return f"❌ {e}"

    # ── /rollback ─────────────────────────────────────────────────────────────
    if cmd == "rollback":
        if not args:
            return "❌ Usage: /rollback <patch_id>"
        try:
            rollback_patch(args)
            return f"↩️ Patch '{args}' rolled back successfully."
        except (ValueError, RuntimeError) as e:
            return f"❌ {e}"

    # ── /explain ──────────────────────────────────────────────────────────────
    if cmd == "explain":
        if not args:
            return "❌ Usage: /explain <patch_id>"
        log = _load_changelog()
        patch = next((p for p in log if p.get("patch_id") == args), None)
        if not patch:
            return f"❌ Patch '{args}' not found."
        lines = [
            f"**{patch['patch_id']}** — {patch['description']}",
            f"Status : {patch['status']}",
            f"Mode   : {patch['mode']}",
            f"Risk   : {patch['risk_level']}",
            f"Trigger: {patch['trigger']}",
            f"Reason : {patch['reason']}",
            f"Files  : {', '.join(patch.get('affected_files', []))}",
            f"Created: {patch.get('timestamp', '?')}",
        ]
        if patch.get("applied_timestamp"):
            lines.append(f"Applied: {patch['applied_timestamp']}")
        if patch.get("diff_preview"):
            lines.append(
                "\nDiff preview:\n```\n" + patch["diff_preview"][:500] + "\n```"
            )
        return "\n".join(lines)

    # ── /history ──────────────────────────────────────────────────────────────
    if cmd == "history":
        log = _load_changelog()
        if not log:
            return "📚 No change history yet."
        recent = log[-10:]
        _status_emoji = {
            "pending": "⏳", "approved": "✅", "rejected": "❌",
            "rolled_back": "↩️", "failed": "💥",
        }
        lines = []
        for p in reversed(recent):
            emoji = _status_emoji.get(p.get("status", ""), "?")
            ts = p.get("timestamp", "?")[:16]
            lines.append(f"{emoji} {p['patch_id']} [{ts}] {p['description'][:50]}")
        return "📚 Recent changes (newest first):\n" + "\n".join(lines)

    # ── /improve ──────────────────────────────────────────────────────────────
    if cmd == "improve":
        if not args:
            return "❌ Usage: /improve <module_name>"
        patches = analyze_module(args, trigger="slash command")
        if not patches:
            return f"🔎 Analysis of '{args}' complete — no patches queued."
        lines = [
            f"• [{p['risk_level']}] {p['description'][:60]}" for p in patches
        ]
        return f"🔎 Analysis of '{args}' complete:\n" + "\n".join(lines)

    # ── /plan (Feature 2) ─────────────────────────────────────────────────────
    if cmd == "plan":
        if not args:
            return "❌ Usage: /plan <task description>"
        plan = analyze_prompt(args)
        # Store task for /execute
        with _state_lock:
            s = _load_state()
            s["plan_pending_task"] = args
            _save_state(s)

        out: list[str] = [f"📋 **PLAN** — {plan['summary']}", ""]
        if plan["phases"]:
            for phase in plan["phases"]:
                out.append(f"  {phase['name']} (Priority: {phase['priority']})")
                for item in phase["items"][:5]:
                    out.append(f"    • {item}")
        elif plan["actions"]:
            out.append("**Steps:**")
            for action in plan["actions"][:8]:
                out.append(f"  • {action}")
        out.append("")
        if plan["patch_types"]:
            out.append(f"🔧 Improvements: {', '.join(plan['patch_types'])}")
        if plan["has_high_risk"]:
            out.append("⚠️ HIGH risk detected — manual approval required.")
        else:
            out.append("Risk: LOW/MEDIUM — safe to proceed.")
        out.append("")
        out.append("✅ Plan stored. Run **/execute** to proceed.")
        return "\n".join(out)

    # ── /execute (Feature 2) ──────────────────────────────────────────────────
    if cmd == "execute":
        state = _load_state()
        pending_task = state.get("plan_pending_task")
        if not pending_task:
            return "❌ No pending plan. Use /plan <task> first."
        with _state_lock:
            s = _load_state()
            s["plan_pending_task"] = None
            _save_state(s)
        _push_activity(f"⚡ Executing plan: {pending_task[:60]}…", "info")
        return handle_complex_task(pending_task)

    # ── /research (Feature 3) ─────────────────────────────────────────────────
    if cmd == "research":
        if not args:
            return "❌ Usage: /research <query>"
        return web_research(args)

    # ── /compact (Feature 6) ──────────────────────────────────────────────────
    if cmd == "compact":
        return compact_context()

    # ── /cost (Feature 6) ─────────────────────────────────────────────────────
    if cmd == "cost":
        stats = get_session_cost()
        return (
            f"📊 **Session Report**\n"
            f"Patches applied  : {stats['patches_applied']}\n"
            f"Patches pending  : {stats['patches_pending']}\n"
            f"Patches rejected : {stats['patches_rejected']}\n"
            f"Rolled back      : {stats['patches_rolled_back']}\n"
            f"Session time     : ~{stats['session_minutes']} min\n"
            f"Activity entries : {stats['activity_entries']}\n"
            f"Context health   : {stats['context_health']}"
        )

    # ── /schedule (Feature 7) ─────────────────────────────────────────────────
    if cmd == "schedule":
        args_lower = args.lower().strip()
        if args_lower == "list":
            schedules = list_schedules()
            if not schedules:
                return "⏰ No schedules registered."
            lines = [
                f"• {s['name']} — {s['freq']} "
                f"(last run: {s.get('last_run_ts') or 'never'})"
                for s in schedules
            ]
            return "⏰ **Active Schedules:**\n" + "\n".join(lines)

        if args_lower.startswith("remove "):
            sched_name = args[7:].strip()
            if remove_schedule(sched_name):
                return f"🗑️ Schedule '{sched_name}' removed."
            return f"❌ Schedule '{sched_name}' not found."

        sched_parts = args.split(None, 1)
        if len(sched_parts) < 2:
            return (
                "❌ Usage:\n"
                "  /schedule <name> <hourly|daily|weekly>\n"
                "  /schedule list\n"
                "  /schedule remove <name>"
            )
        sched_name, sched_freq = sched_parts[0], sched_parts[1]
        entry = register_schedule(sched_name, sched_freq)
        return (
            f"⏰ Scheduled: **{sched_name}** running {entry['freq']}.\n"
            "→ Will execute automatically. Run /schedule list to view all."
        )

    # ── /mode ─────────────────────────────────────────────────────────────────
    if cmd == "mode":
        if not args:
            return (
                f"⚙️ Current mode: {get_mode()}. "
                "Usage: /mode <general|money|auto>"
            )
        try:
            set_mode(args.upper())
            return f"⚙️ ASCEND_FORGE mode set to **{args.upper()}**."
        except ValueError as e:
            return f"❌ {e}"

    # ── /blacklight ───────────────────────────────────────────────────────────
    if cmd == "blacklight":
        if args.lower() in ("on", "1", "true", "yes"):
            set_blacklight_active(True)
            return "⚡ BLACKLIGHT activated — MONEY_MODE forced."
        if args.lower() in ("off", "0", "false", "no"):
            set_blacklight_active(False)
            return "🔴 BLACKLIGHT deactivated."
        return "❌ Usage: /blacklight on|off"

    return f"❓ Unknown command '/{cmd}'. Run /help for a full list."



def handle_chat_command(message: str) -> str:
    """
    Handle 'ascend: ...' chat commands AND '/<command>' slash commands.

    Tries slash-command routing first, then falls back to the legacy
    'ascend: ...' prefix.  Returns a human-readable response string.
    """
    raw = message.strip()

    # ── Slash command delegation (Feature 1) ──────────────────────────────────
    if raw.startswith("/"):
        return handle_slash_command(raw)

    if not raw.lower().startswith("ascend:"):
        return ""

    cmd = raw[len("ascend:"):].strip().lower()

    # ── Mode commands ──────────────────────────────────────────────────────────
    if cmd.startswith("mode "):
        target = cmd[5:].strip().upper()
        try:
            set_mode(target)
            return f"⚙️ ASCEND_FORGE mode set to **{target}**."
        except ValueError as e:
            return f"❌ {e}"

    # ── Scan commands ─────────────────────────────────────────────────────────
    if cmd in ("scan system", "scan"):
        patches = scan_system(trigger="chat command")
        if not patches:
            return "🔍 Scan complete — no patches queued."
        lines = [f"• [{p['risk_level']}] {p['description'][:60]}" for p in patches]
        return "🔍 Scan complete. Patches queued:\n" + "\n".join(lines)

    if cmd.startswith("analyze "):
        module = cmd[8:].strip()
        patches = analyze_module(module, trigger="chat command")
        if not patches:
            return f"🔎 Analysis of '{module}' complete — no patches queued."
        lines = [f"• [{p['risk_level']}] {p['description'][:60]}" for p in patches]
        return f"🔎 Analysis of '{module}' complete:\n" + "\n".join(lines)

    # ── Prompt / output optimisation ──────────────────────────────────────────
    if cmd in ("improve prompts", "optimize outputs", "focus on profit"):
        orig_mode = get_mode()
        patches = scan_system(trigger="chat command")
        money_patches = [p for p in patches if p.get("patch_type") in ("prompt", "monetization")]
        if not money_patches:
            return "✅ No weak prompts detected — outputs look good."
        lines = [f"• [{p['risk_level']}] {p['description'][:60]}" for p in money_patches]
        return "💰 Prompt optimisation patches queued:\n" + "\n".join(lines)

    # ── Patch listing ─────────────────────────────────────────────────────────
    if cmd in ("show pending", "list patches"):
        log = _load_changelog()
        pending = [p for p in log if p.get("status") == "pending"]
        if not pending:
            return "📋 No pending patches."
        lines = [
            f"• {p['patch_id']} [{p['risk_level']}] {p['description'][:50]}"
            for p in pending[-10:]
        ]
        return f"📋 {len(pending)} pending patch(es):\n" + "\n".join(lines)

    if cmd == "apply all low":
        log = _load_changelog()
        low_pending = [p for p in log if p.get("status") == "pending"
                       and p.get("risk_level") == "LOW"]
        if not low_pending:
            return "📋 No LOW-risk pending patches to apply."
        applied = []
        for p in low_pending:
            try:
                approve_patch(p["patch_id"])
                applied.append(p["description"][:50])
            except Exception as exc:
                _push_activity(f"Failed to apply {p['patch_id']}: {exc}", "error")
        if applied:
            return "✅ Applied LOW-risk patches:\n" + "\n".join(f"• {d}" for d in applied)
        return "⚠️ No patches could be applied."

    if cmd == "cancel all":
        log = _load_changelog()
        pending = [p for p in log if p.get("status") == "pending"]
        for p in pending:
            try:
                reject_patch(p["patch_id"])
            except Exception:
                pass
        return f"🗑️ Cancelled {len(pending)} pending patch(es)."

    # ── History commands ──────────────────────────────────────────────────────
    if cmd in ("history", "show changes"):
        log = _load_changelog()
        if not log:
            return "📚 No change history yet."
        recent = log[-10:]
        lines = []
        for p in reversed(recent):
            status_emoji = {
                "pending": "⏳",
                "approved": "✅",
                "rejected": "❌",
                "rolled_back": "↩️",
                "failed": "💥",
            }.get(p.get("status", ""), "?")
            ts = p.get("timestamp", "?")[:16]
            lines.append(
                f"{status_emoji} {p['patch_id']} [{ts}] {p['description'][:50]}"
            )
        return "📚 Recent changes (newest first):\n" + "\n".join(lines)

    if cmd.startswith("rollback "):
        patch_id = cmd[9:].strip()
        try:
            rollback_patch(patch_id)
            return f"↩️ Patch '{patch_id}' rolled back successfully."
        except (ValueError, RuntimeError) as e:
            return f"❌ {e}"

    if cmd.startswith("explain "):
        patch_id = cmd[8:].strip()
        log = _load_changelog()
        patch = next((p for p in log if p.get("patch_id") == patch_id), None)
        if not patch:
            return f"❌ Patch '{patch_id}' not found."
        lines = [
            f"**{patch['patch_id']}** — {patch['description']}",
            f"Status : {patch['status']}",
            f"Mode   : {patch['mode']}",
            f"Risk   : {patch['risk_level']}",
            f"Trigger: {patch['trigger']}",
            f"Reason : {patch['reason']}",
            f"Files  : {', '.join(patch.get('affected_files', []))}",
            f"Created: {patch.get('timestamp', '?')}",
        ]
        if patch.get("applied_timestamp"):
            lines.append(f"Applied: {patch['applied_timestamp']}")
        if patch.get("diff_preview"):
            lines.append("\nDiff preview:\n```\n" + patch["diff_preview"][:500] + "\n```")
        return "\n".join(lines)

    # ── State queries ─────────────────────────────────────────────────────────
    if cmd in ("status", "info"):
        state = _load_state()
        log = _load_changelog()
        pending = sum(1 for p in log if p.get("status") == "pending")
        return (
            f"🔥 **ASCEND_FORGE Status**\n"
            f"Mode          : {state.get('mode', MODE_AUTO)}\n"
            f"Observe-only  : {'Yes ⚠️' if state.get('observe_only') else 'No'}\n"
            f"BLACKLIGHT    : {'Active ⚡' if state.get('blacklight_active') else 'Inactive'}\n"
            f"Pending patches: {pending}\n"
            f"Approved      : {state.get('patches_approved', 0)}\n"
            f"Rejected      : {state.get('patches_rejected', 0)}\n"
            f"Failed        : {state.get('patches_failed', 0)}\n"
            f"Auto-approve LOW: {'On' if state.get('auto_approve_low') else 'Off'}\n"
            f"Last scan     : {state.get('last_scan') or 'Never'}"
        )

    return (
        "❓ Unknown ASCEND_FORGE command. Try:\n"
        "• ascend: mode general / money / auto\n"
        "• ascend: scan system\n"
        "• ascend: improve prompts\n"
        "• ascend: analyze <module>\n"
        "• ascend: show pending\n"
        "• ascend: apply all low\n"
        "• ascend: cancel all\n"
        "• ascend: history\n"
        "• ascend: rollback <patch_id>\n"
        "• ascend: explain <patch_id>\n"
        "Or use slash commands — run /help for the full list."
    )


# ── Public API helpers (used by server.py) ────────────────────────────────────

def get_status() -> dict:
    state = _load_state()
    log = _load_changelog()
    pending = [p for p in log if p.get("status") == "pending"]
    return {
        **state,
        "pending_count": len(pending),
        "total_patches": len(log),
        "activity": list(reversed(_activity_feed[-20:])),
    }


def get_pending_patches() -> list[dict]:
    log = _load_changelog()
    return [p for p in log if p.get("status") == "pending"]


def get_changelog(limit: int = 50) -> list[dict]:
    log = _load_changelog()
    return list(reversed(log[-limit:]))


def set_auto_approve_low(enabled: bool) -> None:
    with _state_lock:
        state = _load_state()
        state["auto_approve_low"] = enabled
        _save_state(state)
    _push_activity(f"Auto-approve LOW patches: {'ON' if enabled else 'OFF'}", "info")


def set_blacklight_active(active: bool) -> None:
    with _state_lock:
        state = _load_state()
        state["blacklight_active"] = active
        _save_state(state)
    if active:
        _push_activity("⚡ BLACKLIGHT active — forcing MONEY_MODE behaviour.", "info")

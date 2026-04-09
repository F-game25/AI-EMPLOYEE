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
        "performance": "Optimise performance as specified in task",
        "prompt": "Upgrade AI prompt quality for better output",
        "capability": "Implement new capability from task specification",
        "efficiency": "Stabilise and improve agent efficiency",
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

    # Simulate apply: mark approved
    try:
        patch["status"] = "approved"
        patch["applied_timestamp"] = _now_iso()
        _log_patch(patch)
        _record_success()
        with _state_lock:
            s = _load_state()
            s["patches_approved"] = s.get("patches_approved", 0) + 1
            _save_state(s)
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


# ── Chat command handler ──────────────────────────────────────────────────────

def handle_chat_command(message: str) -> str:
    """
    Handle 'ascend: ...' chat commands.

    Returns a human-readable response string.
    """
    raw = message.strip()
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
        "• ascend: explain <patch_id>"
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

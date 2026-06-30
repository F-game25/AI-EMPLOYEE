"""HITL-gated desktop (screen/system) control — "computer use" Phase 2.

Deny-by-default. Two gates must BOTH be ON (master Computer-Use switch + the
desktop sub-switch), and the driver (pyautogui) must be present. Read-only screen
capture runs under the gates. EVERY side-effecting action (move/click/type/key/
scroll/drag, and ``run``) ALWAYS requires explicit, per-action human approval:
the model produces a structured plan (what + where), the caller surfaces it for
approval, and only ``execute_approved(plan, approved=True)`` runs it. No
autonomous chaining — each action re-prompts. System commands (``run``) go
through the sandboxed ``shell_exec`` tool, never pyautogui. Every attempt is
audited (secret params redacted).

pyautogui is optional: absent → unavailable (never crashes).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from companion.computer_use_mode import computer_use_enabled, desktop_enabled

logger = logging.getLogger("companion.desktop_control")

# Side-effecting actions — ALWAYS require explicit human approval.
_ACTUATION = {"move", "click", "double_click", "right_click", "drag",
              "type", "press", "hotkey", "scroll"}
_RUN = "run"
_APPROVAL_REQUIRED = _ACTUATION | {_RUN}
_READONLY = {"screenshot"}
_SECRET_PARAM_KEYS = {"text", "password", "secret", "token", "api_key", "command"}


def _pyautogui():
    """Return the optional desktop driver, or ``None`` when unavailable."""
    try:
        import pyautogui  # noqa: PLC0415
        pyautogui.FAILSAFE = True  # slamming the mouse to a screen corner aborts
        return pyautogui
    except Exception as exc:  # noqa: BLE001 — headless / not installed
        logger.warning("desktop driver unavailable (pyautogui): %s", exc)
        return None


def desktop_ready() -> dict:
    """All gates + driver state for desktop control right now."""
    master = computer_use_enabled()
    desk = desktop_enabled()
    driver = _pyautogui() is not None
    return {"master_on": master, "desktop_on": desk, "driver": driver,
            "ready": master and desk and driver}


def _denied(reason: str) -> dict:
    """Return a standardized denial result and log the reason."""
    logger.info("desktop action denied: %s", reason)
    return {"ok": False, "status": "denied", "reason": reason}


def _audit(event: str, **fields) -> None:
    """Write a redacted desktop-control audit event to logs, audit storage, and bus."""
    safe = {k: ("***" if str(k).lower() in _SECRET_PARAM_KEYS else v) for k, v in fields.items()}
    logger.info("AUDIT desktop.%s field_count=%d", event, len(safe))
    try:
        from core.audit_engine import get_audit_engine  # noqa: PLC0415
        get_audit_engine().record(
            actor="desktop_control",
            action=f"desktop_{event}",
            input_data=safe,
            risk_score=0.75 if event.startswith(("execute", "blocked")) else 0.25,
            meta={"surface": "desktop_control"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("desktop audit persistence failed: %s", exc)
    try:  # best-effort; never block on the bus
        from core.bus import get_bus  # noqa: PLC0415
        get_bus().publish("logs", {"surface": "desktop_control", "event": event, **safe})
    except Exception as exc:  # noqa: BLE001
        logger.debug("desktop audit bus publish failed: %s", exc)


def _describe(action: str, p: dict) -> str:
    """Create human-readable text for an approval plan."""
    p = p or {}
    if action in ("click", "double_click", "right_click", "move"):
        at = f"at ({p.get('x')}, {p.get('y')})" if "x" in p else "at current position"
        return f"{action.replace('_', ' ')} {at}"
    if action == "type":
        return f"type {len(str(p.get('text', '')))} characters"
    if action in ("press", "hotkey"):
        return f"press key(s): {p.get('keys') or p.get('key')}"
    if action == "scroll":
        return f"scroll {p.get('amount', 0)}"
    if action == "drag":
        return f"drag to ({p.get('x')}, {p.get('y')})"
    if action == _RUN:
        return f"run command: {str(p.get('command', ''))[:80]}"
    return action


def plan_action(action: str, **params) -> dict:
    """Build an approval-ready plan for a desktop action. Does NOT execute.
    The caller surfaces ``plan`` for human approval, then calls execute_approved."""
    action = str(action or "").strip().lower()
    if action not in _APPROVAL_REQUIRED and action not in _READONLY:
        return _denied(f"unknown desktop action '{action}'")
    needs = action in _APPROVAL_REQUIRED
    return {
        "ok": True,
        "status": "needs_approval" if needs else "ready",
        "plan": {
            "action": action,
            "params": dict(params),
            "what": _describe(action, params),
            "requires_approval": needs,
        },
    }


def screenshot(save_dir: str | None = None) -> dict:
    """Read-only screen capture. Allowed when both gates are ON."""
    if not (computer_use_enabled() and desktop_enabled()):
        return _denied("computer-use desktop mode is OFF")
    pg = _pyautogui()
    if pg is None:
        return _denied("desktop driver (pyautogui) not available")
    try:
        img = pg.screenshot()
        out_dir = _screenshot_dir(save_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"screen-{int(time.time())}.png"
        img.save(path)
        _audit("screenshot", path=str(path), size=list(img.size))
        return {"ok": True, "status": "captured", "path": str(path), "size": list(img.size)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "error": str(exc)}


def execute_approved(plan: dict, *, approved: bool, approver: str = "") -> dict:
    """Execute a side-effecting desktop action — ONLY with explicit approval.

    Deny-by-default: not approved, gates off, no driver, or unknown action → blocked.
    Every attempt is audited.
    """
    plan = plan or {}
    action = str(plan.get("action", "")).strip().lower()
    params = dict(plan.get("params", {}))
    if action not in _APPROVAL_REQUIRED:
        return _denied(f"'{action}' is not an approvable desktop action")
    if not approved:
        _audit("blocked_unapproved", action=action)
        return _denied("action not approved by a human")
    r = desktop_ready()
    if not r["ready"]:
        return _denied(f"desktop control not ready ({r})")
    _audit("execute", action=action, approver=approver or "unknown", **params)
    try:
        if action == _RUN:
            result = _run_command(str(params.get("command", "")))
        else:
            result = _actuate(_pyautogui(), action, params)
        return {"ok": True, "status": "executed", "action": action, "result": result}
    except Exception as exc:  # noqa: BLE001
        logger.error("desktop execute error: %s", exc)
        return {"ok": False, "status": "error", "action": action, "error": str(exc)}


def _actuate(pg, action: str, p: dict) -> Any:
    """Dispatch a pyautogui action after approval and gate checks."""
    x, y = p.get("x"), p.get("y")
    if action == "move":
        pg.moveTo(x, y)
        return "moved"
    if action == "click":
        pg.click(x, y) if x is not None else pg.click()
        return "clicked"
    if action == "double_click":
        pg.doubleClick(x, y) if x is not None else pg.doubleClick()
        return "double_clicked"
    if action == "right_click":
        pg.rightClick(x, y) if x is not None else pg.rightClick()
        return "right_clicked"
    if action == "drag":
        pg.dragTo(x, y, duration=0.2)
        return "dragged"
    if action == "type":
        pg.typewrite(str(p.get("text", "")), interval=0.01)
        return "typed"
    if action == "press":
        pg.press(p.get("key") or p.get("keys"))
        return "pressed"
    if action == "hotkey":
        pg.hotkey(*(p.get("keys") or []))
        return "hotkey"
    if action == "scroll":
        pg.scroll(int(p.get("amount", 0)))
        return "scrolled"
    raise ValueError(f"unhandled actuation '{action}'")


def _run_command(command: str) -> dict:
    """Run a system command through the sandboxed shell_exec tool (never raw)."""
    if not command.strip():
        return {"ok": False, "error": "empty command"}
    from tools.implementations.shell_exec import shell_exec  # noqa: PLC0415
    return shell_exec(command)


def _artifacts_dir() -> Path:
    """Return the controlled artifact root for desktop captures."""
    try:
        from core.state_paths import canonical_state_dir  # noqa: PLC0415
        return canonical_state_dir() / "artifacts"
    except Exception:  # noqa: BLE001 — never repo-local ./state (C0); mirror canonical default
        return Path.home() / ".ai-employee" / "state" / "artifacts"


def _screenshot_dir(save_dir: str | None = None) -> Path:
    """Resolve a screenshot directory under the controlled artifacts root."""
    root = _artifacts_dir().resolve()
    if not save_dir:
        return root
    subdir = Path(save_dir)
    if subdir.is_absolute() or ".." in subdir.parts:
        logger.warning("ignoring unsafe desktop screenshot save_dir")
        return root
    candidate = (root / subdir).resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    logger.warning("ignoring desktop screenshot save_dir outside artifacts")
    return root

"""Persistent store for work opportunities + their lifecycle state.

Backed by a single JSON file (``work_opportunities.json``) under the canonical
state dir, guarded by the repo's fcntl file lock. Pure persistence + status
transitions — no business logic, no LLM, no external I/O.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

# ── Lifecycle states (the work_lifecycle state machine moves between these) ────
# ingest → evaluate → quote(approval) → accepted → execute → deliver(approval)
#        → feedback → study
STATES: tuple[str, ...] = (
    "ingested",            # raw opportunity captured
    "evaluated",           # fit/value/effort/risk scored
    "quote_pending",       # quote drafted, awaiting HITL approval (HARD GATE 1)
    "quoted",              # quote approved (ready to be accepted by client)
    "accepted",            # client accepted the quote
    "executing",           # deliverable being built
    "delivery_pending",    # deliverable staged, awaiting HITL approval (HARD GATE 2)
    "delivered",           # deliverable approved + released
    "feedback_recorded",   # outcome/rating captured
    "studied",             # offline study lesson attached
    "declined",            # we declined to pursue
    "failed",              # an executor reported a hard failure
)

# Allowed forward transitions. study/feedback/decline/fail are reachable from
# most states; the happy path is the ordered list above.
_ALLOWED: dict[str, set[str]] = {
    "ingested":          {"evaluated", "declined", "failed"},
    "evaluated":         {"quote_pending", "declined", "failed"},
    "quote_pending":     {"quoted", "declined", "failed"},
    "quoted":            {"accepted", "declined", "failed"},
    # deliver() may build the artifact itself, so delivery_pending is reachable
    # directly from accepted (no separate execute call) as well as from executing.
    "accepted":          {"executing", "delivery_pending", "declined", "failed"},
    "executing":         {"delivery_pending", "failed"},
    "delivery_pending":  {"delivered", "failed"},
    "delivered":         {"feedback_recorded", "failed"},
    "feedback_recorded": {"studied"},
    "studied":           set(),
    "declined":          set(),
    "failed":            set(),
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_file() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        base = canonical_state_dir()
    except Exception:
        base = Path.home() / ".ai-employee" / "state"  # canonical default, never repo-local (C0)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "work_opportunities.json"


def _load() -> dict[str, Any]:
    path = _state_file()
    try:
        from core.file_lock import read_json_safe
        data = read_json_safe(path, default={"opportunities": {}})
    except Exception:
        data = None
    if not isinstance(data, dict) or "opportunities" not in data:
        data = {"opportunities": {}}
    return data


def _save(data: dict[str, Any]) -> bool:
    path = _state_file()
    try:
        from core.file_lock import write_json_safe
        return bool(write_json_safe(path, data))
    except Exception:
        # Last-resort direct write so we never silently lose state.
        try:
            import json
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create(opportunity: dict[str, Any] | None) -> dict[str, Any]:
    """Persist a new opportunity in state ``ingested``. Never raises."""
    src = dict(opportunity or {})
    oid = src.get("id") or f"opp-{uuid.uuid4().hex[:10]}"
    record = {
        "id": oid,
        "title": str(src.get("title") or src.get("name") or "Untitled opportunity"),
        "description": str(src.get("description") or ""),
        "source": str(src.get("source") or "manual"),
        "category": str(src.get("category") or "general"),
        "client": dict(src.get("client") or {}),
        "budget_hint": src.get("budget_hint"),
        "deadline": src.get("deadline"),
        "tags": list(src.get("tags") or []),
        "raw": {k: v for k, v in src.items() if k not in {
            "id", "title", "name", "description", "source", "category",
            "client", "budget_hint", "deadline", "tags",
        }},
        "status": "ingested",
        "created_at": _now(),
        "updated_at": _now(),
        "evaluation": None,
        "quote": None,
        "deliverable": None,
        "feedback": None,
        "study": None,
        "gates": {},          # gate_name → {gate_id, status}
        "history": [{"state": "ingested", "at": _now()}],
    }
    data = _load()
    data["opportunities"][oid] = record
    _save(data)
    return record


def get(opp_id: str) -> dict[str, Any] | None:
    return _load()["opportunities"].get(str(opp_id))


def list_all(status: str | None = None) -> list[dict[str, Any]]:
    items = list(_load()["opportunities"].values())
    if status:
        items = [o for o in items if o.get("status") == status]
    items.sort(key=lambda o: o.get("created_at", ""), reverse=True)
    return items


def update_fields(opp_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    data = _load()
    rec = data["opportunities"].get(str(opp_id))
    if rec is None:
        return None
    for k, v in (fields or {}).items():
        if k in {"id", "status", "history"}:
            continue  # protected — status only via set_status
        rec[k] = v
    rec["updated_at"] = _now()
    _save(data)
    return rec


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED.get(current, set())


def set_status(opp_id: str, target: str, *, force: bool = False) -> dict[str, Any]:
    """Transition an opportunity to ``target``. Returns structured result.

    Refuses illegal transitions unless ``force`` (used only for failure paths).
    Never raises.
    """
    if target not in STATES:
        return {"ok": False, "error": f"unknown state: {target}"}
    data = _load()
    rec = data["opportunities"].get(str(opp_id))
    if rec is None:
        return {"ok": False, "error": "opportunity not found"}
    current = rec.get("status", "ingested")
    if current == target:
        return {"ok": True, "opportunity": rec, "noop": True}
    if not force and not can_transition(current, target):
        return {
            "ok": False,
            "error": f"illegal transition {current} → {target}",
            "current": current,
        }
    rec["status"] = target
    rec["updated_at"] = _now()
    rec.setdefault("history", []).append({"state": target, "at": _now(), "from": current})
    _save(data)
    return {"ok": True, "opportunity": rec}


def attach(opp_id: str, key: str, value: Any) -> dict[str, Any] | None:
    """Attach a sub-document (evaluation/quote/deliverable/feedback/study/gate)."""
    data = _load()
    rec = data["opportunities"].get(str(opp_id))
    if rec is None:
        return None
    rec[key] = value
    rec["updated_at"] = _now()
    _save(data)
    return rec


def record_gate(opp_id: str, gate_name: str, gate_info: dict[str, Any]) -> dict[str, Any] | None:
    data = _load()
    rec = data["opportunities"].get(str(opp_id))
    if rec is None:
        return None
    rec.setdefault("gates", {})[gate_name] = gate_info
    rec["updated_at"] = _now()
    _save(data)
    return rec


def delete(opp_id: str) -> bool:
    data = _load()
    if str(opp_id) in data["opportunities"]:
        del data["opportunities"][str(opp_id)]
        _save(data)
        return True
    return False

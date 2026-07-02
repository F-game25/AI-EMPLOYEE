"""PublishQueue — staged content awaiting human approval before it can go live.

The queue NEVER posts to any external platform. Approval marks an item 'approved'
(ready for a human/integration to publish); there is no autonomous send. State is
a JSON file under the canonical state dir.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.RLock()
_FILE = "content_publish_queue.json"


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:  # noqa: BLE001 — never repo-local ./state (C0); mirror canonical default
        return Path.home() / ".ai-employee" / "state"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PublishQueue:
    """Approval-gated queue of content items. No item is ever auto-published."""

    def __init__(self) -> None:
        self._path = _state_dir() / _FILE

    def _load(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception:  # noqa: BLE001 — corrupt file → start clean, don't crash
            return []

    def _save(self, items: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self._path)

    def enqueue(self, *, topic: str, platform: str, artifact_path: str | None,
                word_count: int = 0, content_status: str = "draft") -> dict:
        """Stage a content item as pending_approval (never auto-posts)."""
        entry = {
            "id": str(uuid.uuid4())[:8],
            "topic": topic,
            "platform": platform,
            "artifact_path": artifact_path,
            "word_count": int(word_count or 0),
            "content_status": content_status,   # draft (LLM) | template (offline)
            "status": "pending_approval",       # pending_approval → approved | rejected
            "created_at": _now(),
            "decided_at": None,
            "gate_id": None,
        }
        with _LOCK:
            items = self._load()
            items.append(entry)
            self._save(items)
        return entry

    def list(self, status: str | None = None) -> list[dict]:
        items = self._load()
        return [i for i in items if not status or i.get("status") == status]

    def get(self, entry_id: str) -> dict | None:
        return next((i for i in self._load() if i.get("id") == entry_id), None)

    def approve(self, entry_id: str, approved_by: str = "operator") -> dict:
        """Approve via the HITL gate. Marks 'approved' (ready) — does NOT post."""
        with _LOCK:
            items = self._load()
            entry = next((i for i in items if i.get("id") == entry_id), None)
            if entry is None:
                return {"ok": False, "error": f"entry '{entry_id}' not found"}
            if entry["status"] != "pending_approval":
                return {"ok": False, "error": f"entry is '{entry['status']}', not pending_approval"}
            gate = {"approved": True}
            try:
                from core.hitl_gate import get_hitl_gate
                gate = get_hitl_gate().require_approval(
                    agent="content_factory", action="publish_content",
                    payload={"entry_id": entry_id, "platform": entry["platform"],
                             "topic": entry["topic"]},
                    submitted_by=approved_by, blocking=False,
                )
            except Exception as exc:  # noqa: BLE001 — fail closed
                return {"ok": False, "error": f"approval gate unavailable: {exc}"}
            entry["gate_id"] = gate.get("request_id")
            if not gate.get("approved"):
                # Pending human decision via dashboard — not yet publishable.
                self._save(items)
                return {"ok": True, "status": "pending_approval", "gate_id": entry["gate_id"],
                        "note": "queued for human approval before publishing"}
            entry["status"] = "approved"
            entry["decided_at"] = _now()
            self._save(items)
        return {"ok": True, "status": "approved", "entry": entry,
                "note": "approved & ready to publish — no autonomous post performed"}

    def reject(self, entry_id: str) -> dict:
        with _LOCK:
            items = self._load()
            entry = next((i for i in items if i.get("id") == entry_id), None)
            if entry is None:
                return {"ok": False, "error": f"entry '{entry_id}' not found"}
            entry["status"] = "rejected"
            entry["decided_at"] = _now()
            self._save(items)
        return {"ok": True, "status": "rejected", "entry": entry}


_instance: PublishQueue | None = None
_instance_lock = threading.Lock()


def get_publish_queue() -> PublishQueue:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = PublishQueue()
    return _instance

"""Per-session rolling conversation state for the Companion Gateway.

This is the short-term memory a real teammate keeps within a single chat: what
the user is doing, what was just said, what options were offered, what decision
is pending, what the active task looks like, and the most recent tool results.
It is loaded before *every* model call and updated after every turn so a follow
-up like "optie 2" / "do that" resolves against the assistant's own last reply
— never re-asking for context.

Persistence
-----------
One JSON document per ``session_id`` at ``<state>/sessions/<id>.json`` under the
canonical state dir, written through ``core.file_lock`` so concurrent turns on
the same session don't corrupt the file. Tenant isolation reuses the existing
``_tenant_data`` segregation in ``file_lock`` (one file per session, tenant key
inside). Bad/missing files degrade to an empty state — never raise to the
runtime.

No fabrication: ``last_options_given`` is only populated from text that actually
appeared in an assistant reply. Compression (``session_compressor``) keeps the
rolling state compact so the model context never grows unbounded.

Public surface
--------------
    from companion.session_state import get_session_store
    store = get_session_store()
    state = store.load(session_id, tenant_id)
    store.save(state)
    state.note_user(text); state.note_assistant(reply, intent=intent)
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from core.state_paths import canonical_state_dir
from core.file_lock import read_json_safe, write_json_safe

logger = logging.getLogger("companion.session_state")

# Cap the rolling history we keep raw before it gets compressed/dropped.
_MAX_RECENT_MESSAGES = 20
_MAX_TOOL_RESULTS = 8
_MAX_OPTIONS = 12
# Above this many raw messages we compress older ones into a topic summary.
_COMPRESS_AFTER = 16

# A safe-ish session id: filesystem-friendly, no traversal.
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")

# Enumerated-option detection for capturing what the assistant offered.
#   "1) do x", "2. do y", "Option 3: …", "- foo" (only when 2+ present)
_NUMBERED_OPTION = re.compile(
    r"^\s*(?:option\s+|optie\s+|choice\s+)?(\d+)\s*[\).:\-]\s+(.+\S)\s*$",
    re.IGNORECASE)
_BULLET_OPTION = re.compile(r"^\s*[-*•]\s+(.+\S)\s*$")


def _safe_session_id(session_id: str) -> str:
    sid = _SAFE_ID.sub("_", str(session_id or "").strip()) or "anonymous"
    return sid[:120]


@dataclass
class SessionState:
    """Rolling per-session state. Plain dataclass for clean JSON transport."""

    session_id: str
    tenant_id: str = "default"
    current_topic: str = ""
    last_user_message: str = ""
    last_assistant_message: str = ""
    last_options_given: list[dict[str, Any]] = field(default_factory=list)
    pending_decision: Optional[dict[str, Any]] = None
    active_task_state: Optional[dict[str, Any]] = None
    recent_tool_results: list[dict[str, Any]] = field(default_factory=list)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], session_id: str,
                  tenant_id: str = "default") -> "SessionState":
        data = data or {}
        return cls(
            session_id=session_id,
            tenant_id=data.get("tenant_id", tenant_id),
            current_topic=str(data.get("current_topic", "") or ""),
            last_user_message=str(data.get("last_user_message", "") or ""),
            last_assistant_message=str(data.get("last_assistant_message", "") or ""),
            last_options_given=list(data.get("last_options_given") or []),
            pending_decision=data.get("pending_decision") or None,
            active_task_state=data.get("active_task_state") or None,
            recent_tool_results=list(data.get("recent_tool_results") or []),
            recent_messages=list(data.get("recent_messages") or []),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
        )

    # ── Mutation helpers ─────────────────────────────────────────────────────

    def note_user(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        self.last_user_message = text
        self.recent_messages.append({"role": "user", "content": text, "ts": time.time()})
        self._trim_messages()

    def note_assistant(self, text: str, *, intent: Optional[dict] = None,
                       actions: Optional[list] = None,
                       tool_results: Optional[list] = None) -> None:
        """Record the assistant reply + capture any enumerated options from it.

        ``last_options_given`` is rebuilt from the reply text every turn: if this
        reply offered options they become the new set; if it offered none, the
        prior set is cleared (the offer is stale once a non-option reply lands).
        """
        text = str(text or "").strip()
        if text:
            self.last_assistant_message = text
            self.recent_messages.append(
                {"role": "assistant", "content": text, "ts": time.time()})
        self.last_options_given = extract_options(text)
        if intent:
            topic = str(intent.get("task_type") or intent.get("mode") or "").strip()
            if topic:
                self.current_topic = topic
        for tr in (tool_results or []):
            if isinstance(tr, dict):
                self.recent_tool_results.append(tr)
        if actions:
            # Surface a lightweight pending decision when an action awaits the
            # user (e.g. an approval) so "do that / yes" has a referent.
            pending = next((a for a in actions
                            if isinstance(a, dict)
                            and str(a.get("status", "")).lower()
                            in ("waiting_approval", "awaiting_approval", "proposed")),
                           None)
            self.pending_decision = pending or self.pending_decision
        self.recent_tool_results = self.recent_tool_results[-_MAX_TOOL_RESULTS:]
        self._trim_messages()
        self.updated_at = time.time()

    def set_active_task(self, task: Optional[dict]) -> None:
        self.active_task_state = task or None

    def _trim_messages(self) -> None:
        if len(self.recent_messages) > _MAX_RECENT_MESSAGES:
            self.recent_messages = self.recent_messages[-_MAX_RECENT_MESSAGES:]

    def compact(self) -> None:
        """Compress older history into ``current_topic`` to bound context size.

        Reuses ``session_compressor`` heuristics (no LLM by default). Older
        messages beyond the recent window are summarized into durable context
        nodes and dropped from the raw rolling window. Failure is non-fatal —
        we still hard-trim the raw list so it can never grow unbounded.
        """
        if len(self.recent_messages) <= _COMPRESS_AFTER:
            return
        half = max(1, _MAX_RECENT_MESSAGES // 2)
        old = self.recent_messages[:-half]
        keep = self.recent_messages[-half:]
        try:
            from memory.context_db.session_compressor import compress_session
            result = compress_session(old, project_id=_safe_session_id(self.session_id),
                                      tenant=self.tenant_id)
            counts = result.get("counts") or {}
            if counts and not self.current_topic:
                self.current_topic = ", ".join(f"{k}:{v}" for k, v in counts.items())
        except Exception as exc:  # noqa: BLE001 — compression is best-effort
            logger.debug("session compaction skipped: %s", exc)
        self.recent_messages = keep

    # ── Read helpers the runtime uses to build context ───────────────────────

    def as_context(self) -> dict[str, Any]:
        """Compact dict the runtime folds into the model context/system prompt."""
        return {
            "current_topic": self.current_topic,
            "last_user_message": self.last_user_message,
            "last_assistant_message": self.last_assistant_message,
            "last_options_given": self.last_options_given,
            "pending_decision": self.pending_decision,
            "active_task_state": self.active_task_state,
            "recent_tool_results": self.recent_tool_results,
        }


def extract_options(text: str) -> list[dict[str, Any]]:
    """Pull enumerated options out of an assistant reply (no fabrication).

    Returns ``[{id, summary}]`` for each detected option. Numbered options win;
    bullet lists count only when there are 2+ of them (a single bullet isn't an
    option set). ``id`` is the 1-based ordinal as a string so "option 2" maps to
    ``id == "2"``.
    """
    text = str(text or "")
    if not text.strip():
        return []
    numbered: list[dict[str, Any]] = []
    bullets: list[str] = []
    for line in text.splitlines():
        m = _NUMBERED_OPTION.match(line)
        if m:
            numbered.append({"id": str(int(m.group(1))),
                             "summary": _clip(m.group(2))})
            continue
        b = _BULLET_OPTION.match(line)
        if b:
            bullets.append(_clip(b.group(1)))
    if numbered:
        # De-dupe by id, keep first occurrence, preserve order.
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for opt in numbered:
            if opt["id"] in seen:
                continue
            seen.add(opt["id"])
            out.append(opt)
        return out[:_MAX_OPTIONS]
    if len(bullets) >= 2:
        return [{"id": str(i + 1), "summary": s}
                for i, s in enumerate(bullets[:_MAX_OPTIONS])]
    return []


def _clip(s: str, n: int = 200) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


class SessionStore:
    """Loads/persists ``SessionState`` per session id, lock-protected."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        sessions_dir = canonical_state_dir() / "sessions"
        return sessions_dir / f"{_safe_session_id(session_id)}.json"

    def load(self, session_id: str, tenant_id: str = "default") -> SessionState:
        sid = str(session_id or "").strip()
        if not sid:
            return SessionState(session_id="anonymous", tenant_id=tenant_id)
        data = read_json_safe(self._path(sid), default={}, tenant_id=tenant_id)
        if not isinstance(data, dict):
            data = {}
        return SessionState.from_dict(data, session_id=sid, tenant_id=tenant_id)

    def save(self, state: SessionState) -> bool:
        if not state or not str(state.session_id or "").strip():
            return False
        state.compact()
        state.updated_at = time.time()
        with self._lock:
            return write_json_safe(self._path(state.session_id),
                                   state.to_dict(), tenant_id=state.tenant_id)


_STORE: Optional[SessionStore] = None
_STORE_LOCK = threading.Lock()


def get_session_store() -> SessionStore:
    """Return the process-wide ``SessionStore`` singleton."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = SessionStore()
    return _STORE

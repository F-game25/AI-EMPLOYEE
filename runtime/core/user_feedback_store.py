"""User Feedback Store — thumbs-up / thumbs-down on agent outputs.

Responsibilities
────────────────
1. Persist every feedback event to ``state/user_feedback.jsonl``.
2. Map the rating to a reinforcement reward signal and forward it to the
   :class:`~core.learning_engine.LearningEngine` so agent strategy weights
   are updated in real time.
3. Optionally propagate the signal to the :class:`~core.memory_index.MemoryIndex`
   when the caller supplies ``memory_ids`` (IDs of memories that informed the
   output being rated).
4. Emit an audit record for every submitted rating via
   :class:`~core.audit_engine.AuditEngine`.

────────────────────────────────────────────────────────────────
RATING → REWARD MAPPING
────────────────────────────────────────────────────────────────

  "up"       →  +1.0  (strongly positive)
  "down"     →  -1.0  (strongly negative)

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.user_feedback_store import get_feedback_store

    store = get_feedback_store()

    # Submit thumbs-up
    entry = store.submit(
        output_id="resp-abc123",
        rating="up",
        agent_id="company-builder",
        actor="user:alice",
        text="Really helpful breakdown!",
    )

    # Get all feedback for one output
    items = store.get_for_output("resp-abc123")

    # Per-agent aggregate
    summary = store.summary_for_agent("company-builder")

    # Recent entries (newest first)
    recent = store.list_recent(limit=50)

    # All-agents aggregate
    global_summary = store.summary()

────────────────────────────────────────────────────────────────
CONFIGURATION
────────────────────────────────────────────────────────────────

  FEEDBACK_STORE_PATH — override path to the JSONL file (optional)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

logger = logging.getLogger("ai_employee.user_feedback")

# ── Types ─────────────────────────────────────────────────────────────────────

Rating = Literal["up", "down"]

_REWARD_MAP: dict[str, float] = {
    "up":   1.0,
    "down": -1.0,
}


# ── Data structure ─────────────────────────────────────────────────────────────

@dataclass
class FeedbackEntry:
    """A single user-feedback event."""

    id:         str             # Unique event id
    ts:         str             # ISO-8601 UTC timestamp
    output_id:  str             # ID of the output being rated (e.g. chat message id)
    rating:     str             # "up" or "down"
    reward:     float           # Numeric reward signal (-1.0 or +1.0)
    agent_id:   str             # Agent that produced the output
    actor:      str             # User who submitted the feedback
    text:       str             # Optional free-text feedback (may be empty)
    memory_ids: list[str]       = field(default_factory=list)  # Memory IDs used in output
    meta:       dict[str, Any]  = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Utility ───────────────────────────────────────────────────────────────────

def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_dir() -> Path:
    ai_home = os.environ.get("AI_HOME", "")
    base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
    return base / "state"


def _default_path() -> Path:
    custom = os.environ.get("FEEDBACK_STORE_PATH", "").strip()
    if custom:
        return Path(custom)
    return _state_dir() / "user_feedback.jsonl"


# ── Store ─────────────────────────────────────────────────────────────────────

class UserFeedbackStore:
    """Persistent store for user feedback on agent outputs.

    All public methods are thread-safe.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path  = path or _default_path()
        self._lock  = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Core: submit ─────────────────────────────────────────────────────────

    def submit(
        self,
        *,
        output_id:  str,
        rating:     Rating,
        agent_id:   str  = "",
        actor:      str  = "user:default",
        text:       str  = "",
        memory_ids: list[str] | None = None,
        meta:       dict[str, Any] | None = None,
    ) -> FeedbackEntry:
        """Record a thumbs-up or thumbs-down rating for an agent output.

        Parameters
        ----------
        output_id:  Identifier of the output being rated.
        rating:     ``"up"`` or ``"down"``.
        agent_id:   Agent that produced the output (for learning integration).
        actor:      User or system submitting the feedback.
        text:       Optional free-text comment from the user.
        memory_ids: IDs of :class:`~core.memory_index.MemoryIndex` entries
                    that informed the output, used for memory reinforcement.
        meta:       Extra structured data attached to the event.

        Returns
        -------
        :class:`FeedbackEntry` — the persisted record.
        """
        rating = _validate_rating(rating)
        reward = _REWARD_MAP[rating]

        entry = FeedbackEntry(
            id         = f"fb-{uuid.uuid4().hex[:12]}",
            ts         = _iso_now(),
            output_id  = (output_id or "").strip(),
            rating     = rating,
            reward     = reward,
            agent_id   = (agent_id or "").strip(),
            actor      = (actor or "user:default").strip(),
            text       = (text or "").strip()[:2000],
            memory_ids = list(memory_ids or []),
            meta       = dict(meta or {}),
        )

        self._persist(entry)
        self._forward_to_learning_engine(entry)
        self._forward_to_memory_index(entry)
        self._record_audit(entry)

        logger.info(
            "Feedback submitted [%s] output_id=%s agent=%s actor=%s reward=%+.1f",
            entry.id, entry.output_id, entry.agent_id, entry.actor, reward,
        )
        return entry

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_for_output(self, output_id: str) -> list[FeedbackEntry]:
        """Return all feedback entries for a specific output ID."""
        target = (output_id or "").strip()
        with self._lock:
            return [e for e in self._load_all() if e.output_id == target]

    def list_recent(self, *, limit: int = 100) -> list[FeedbackEntry]:
        """Return the most recent *limit* entries (newest first)."""
        limit = max(1, int(limit))
        with self._lock:
            return list(reversed(self._load_all()))[:limit]

    def summary_for_agent(self, agent_id: str) -> dict[str, Any]:
        """Return aggregate stats for one agent."""
        target = (agent_id or "").strip()
        with self._lock:
            entries = [e for e in self._load_all() if e.agent_id == target]
        return _aggregate(entries, label=target)

    def summary(self) -> dict[str, Any]:
        """Return a global aggregate across all agents."""
        with self._lock:
            entries = self._load_all()
        total = _aggregate(entries, label="all")
        by_agent: dict[str, Any] = {}
        for e in entries:
            aid = e.agent_id or "__unknown__"
            by_agent.setdefault(aid, []).append(e)
        total["by_agent"] = {
            aid: _aggregate(items, label=aid)
            for aid, items in by_agent.items()
        }
        return total

    # ── Internal ─────────────────────────────────────────────────────────────

    def _persist(self, entry: FeedbackEntry) -> None:
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry.to_dict()) + "\n")
            except Exception as exc:
                logger.warning("Failed to persist feedback entry %s: %s", entry.id, exc)

    def _load_all(self) -> list[FeedbackEntry]:
        """Load all entries from disk.  Caller must hold ``self._lock``."""
        if not self._path.exists():
            return []
        entries: list[FeedbackEntry] = []
        try:
            for line in self._path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entries.append(_dict_to_entry(d))
                except Exception:
                    pass  # Skip malformed lines
        except Exception as exc:
            logger.warning("Failed to load feedback store: %s", exc)
        return entries

    def _forward_to_learning_engine(self, entry: FeedbackEntry) -> None:
        """Reinforce agent strategy weights using the feedback reward."""
        if not entry.agent_id:
            return
        try:
            from core.learning_engine import get_learning_engine  # type: ignore
            eng = get_learning_engine()
            strategy_id = f"agent:{entry.agent_id}"
            eng.record_task(
                task_input     = entry.output_id or "user_feedback",
                chosen_agent   = entry.agent_id,
                strategy_used  = strategy_id,
                result         = {
                    "feedback_id": entry.id,
                    "rating":      entry.rating,
                    "text":        entry.text,
                },
                success_score  = entry.reward,
                decision_reason= f"user_feedback:{entry.rating}",
            )
        except Exception as exc:
            logger.warning("Could not forward feedback to LearningEngine: %s", exc)

    def _forward_to_memory_index(self, entry: FeedbackEntry) -> None:
        """Reinforce (or weaken) memories that informed the rated output."""
        if not entry.memory_ids:
            return
        try:
            from core.memory_index import MemoryIndex, _state_path  # type: ignore
            mi = MemoryIndex(_state_path())
            # Build dummy memory dicts that apply_feedback can match by id
            fake_mems = [{"id": mid} for mid in entry.memory_ids]
            mi.apply_feedback(fake_mems, entry.reward * 0.5)  # damped signal
        except Exception as exc:
            logger.warning("Could not forward feedback to MemoryIndex: %s", exc)

    def _record_audit(self, entry: FeedbackEntry) -> None:
        """Emit a LOW-risk audit record for every feedback submission."""
        try:
            from core.audit_engine import get_audit_engine  # type: ignore
            get_audit_engine().record(
                actor       = entry.actor,
                action      = "user_feedback",
                input_data  = {
                    "output_id": entry.output_id,
                    "rating":    entry.rating,
                    "text":      entry.text[:200] if entry.text else "",
                },
                output_data = {
                    "feedback_id": entry.id,
                    "reward":      entry.reward,
                    "agent_id":    entry.agent_id,
                },
                risk_score  = 0.05,
            )
        except Exception as exc:
            logger.warning("Could not emit audit record for feedback %s: %s", entry.id, exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_rating(value: str) -> Rating:
    v = (value or "").strip().lower()
    if v not in _REWARD_MAP:
        raise ValueError(f"rating must be 'up' or 'down', got: {value!r}")
    return v  # type: ignore[return-value]


def _dict_to_entry(d: dict[str, Any]) -> FeedbackEntry:
    return FeedbackEntry(
        id         = str(d.get("id", "")),
        ts         = str(d.get("ts", "")),
        output_id  = str(d.get("output_id", "")),
        rating     = str(d.get("rating", "up")),
        reward     = float(d.get("reward", 0.0)),
        agent_id   = str(d.get("agent_id", "")),
        actor      = str(d.get("actor", "")),
        text       = str(d.get("text", "")),
        memory_ids = list(d.get("memory_ids", [])),
        meta       = dict(d.get("meta", {})),
    )


def _aggregate(entries: list[FeedbackEntry], *, label: str = "") -> dict[str, Any]:
    total   = len(entries)
    up      = sum(1 for e in entries if e.rating == "up")
    down    = total - up
    rewards = [e.reward for e in entries]
    avg_r   = round(sum(rewards) / total, 4) if total else 0.0
    return {
        "label":        label,
        "total":        total,
        "thumbs_up":    up,
        "thumbs_down":  down,
        "avg_reward":   avg_r,
        "positive_rate": round(up / total, 4) if total else 0.0,
    }


# ── Singleton ─────────────────────────────────────────────────────────────────

_store_instance: Optional[UserFeedbackStore] = None
_store_lock     = threading.Lock()


def get_feedback_store() -> UserFeedbackStore:
    """Return the process-wide :class:`UserFeedbackStore` singleton."""
    global _store_instance
    with _store_lock:
        if _store_instance is None:
            _store_instance = UserFeedbackStore()
    return _store_instance

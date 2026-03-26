"""Memory Store — persistent per-lead conversation history.

Stores and retrieves conversation history for each lead as JSON files.
Designed to be upgradeable to a vector database (e.g. ChromaDB, Pinecone)
by replacing the backend while keeping the same public API.

Storage layout:
    ~/.ai-employee/state/memory/<lead_id>.json
        {
          "lead_id": "abc12345",
          "created_at": "2026-01-01T00:00:00Z",
          "updated_at": "2026-01-01T00:00:00Z",
          "turns": [
            {"role": "assistant", "content": "...", "ts": "..."},
            {"role": "user",      "content": "...", "ts": "..."}
          ],
          "summary": "..."   # optional AI-generated summary for long histories
        }

Usage:
    from memory_store import MemoryStore

    mem = MemoryStore()
    mem.add_turn(lead_id="abc123", role="assistant", content="Hello!")
    history = mem.get_history(lead_id="abc123")
    mem.clear(lead_id="abc123")
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

# Maximum turns to keep in memory before trimming (oldest turns removed first).
# Increase or set to 0 to keep unlimited history.
_DEFAULT_MAX_TURNS = int(os.environ.get("MEMORY_MAX_TURNS", "50"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MemoryStore:
    """Persistent per-lead conversation history backed by JSON files.

    Each lead's history is stored in a separate JSON file under
    ``<AI_HOME>/state/memory/<lead_id>.json``.

    The class is intentionally simple so it can be swapped out for a
    vector-database backend (ChromaDB, Pinecone, Weaviate) later without
    changing callers — just replace this class while keeping the same
    method signatures.
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        max_turns: int = _DEFAULT_MAX_TURNS,
    ) -> None:
        self._dir = storage_dir or (AI_HOME / "state" / "memory")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_turns = max_turns

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _path(self, lead_id: str) -> Path:
        # Sanitise lead_id: keep only alphanumeric, dash, underscore
        safe = "".join(c for c in lead_id if c.isalnum() or c in ("-", "_"))[:64]
        return self._dir / f"{safe}.json"

    def _load(self, lead_id: str) -> dict:
        p = self._path(lead_id)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        return {
            "lead_id": lead_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "turns": [],
            "summary": "",
        }

    def _save(self, data: dict) -> None:
        data["updated_at"] = _now_iso()
        p = self._path(data["lead_id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_turn(self, lead_id: str, role: str, content: str) -> None:
        """Append a single conversation turn for a lead.

        Args:
            lead_id: Unique lead identifier.
            role:    "user" | "assistant" | "system"
            content: Message text.
        """
        data = self._load(lead_id)
        data["turns"].append({"role": role, "content": content, "ts": _now_iso()})
        # Trim to max_turns (keep the most recent ones)
        if self._max_turns > 0 and len(data["turns"]) > self._max_turns:
            data["turns"] = data["turns"][-self._max_turns:]
        self._save(data)

    def get_history(
        self,
        lead_id: str,
        last_n: Optional[int] = None,
        as_messages: bool = True,
    ) -> list:
        """Return conversation history for a lead.

        Args:
            lead_id:     Unique lead identifier.
            last_n:      If set, return only the last N turns.
            as_messages: When True (default) return OpenAI-style message dicts
                         ``[{"role": ..., "content": ...}, ...]``.
                         When False, return the raw turn dicts including "ts".

        Returns:
            List of message dicts (empty list if no history).
        """
        data = self._load(lead_id)
        turns = data.get("turns", [])
        if last_n:
            turns = turns[-last_n:]
        if as_messages:
            return [{"role": t["role"], "content": t["content"]} for t in turns]
        return turns

    def get_summary(self, lead_id: str) -> str:
        """Return the stored summary for a lead (may be empty)."""
        return self._load(lead_id).get("summary", "")

    def set_summary(self, lead_id: str, summary: str) -> None:
        """Store an AI-generated summary for a lead's history."""
        data = self._load(lead_id)
        data["summary"] = summary
        self._save(data)

    def clear(self, lead_id: str) -> None:
        """Delete all stored memory for a lead."""
        p = self._path(lead_id)
        if p.exists():
            p.unlink()

    def list_leads(self) -> list:
        """Return a list of lead IDs that have stored memory."""
        return [p.stem for p in self._dir.glob("*.json")]

    def get_metadata(self, lead_id: str) -> dict:
        """Return metadata (lead_id, created_at, updated_at, turn_count, has_summary)."""
        data = self._load(lead_id)
        return {
            "lead_id": data["lead_id"],
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "turn_count": len(data.get("turns", [])),
            "has_summary": bool(data.get("summary", "")),
        }

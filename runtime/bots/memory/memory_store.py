"""Memory Store — persistent per-entity memory for AI agents.

Gives every agent the ability to remember customers, conversations, leads,
and any context across sessions. Uses a flat-file JSON store that can be
swapped out for a vector DB (Chroma / Pinecone) later without API changes.

Storage layout (all under AI_HOME):
    state/memory/<entity_id>.json          — entity memory file
    state/memory/_index.json               — lightweight global index

Memory record structure:
    {
        "entity_id":   "lead_abc123",        — unique ID (lead / customer / topic)
        "entity_type": "lead",               — "lead" | "customer" | "topic" | "agent"
        "created_at":  "2026-01-01T00:00Z",
        "updated_at":  "2026-01-01T00:00Z",
        "facts":       [{"key": "...", "value": "...", "ts": "..."}],
        "conversation": [
            {"role": "user", "content": "...", "ts": "..."},
            {"role": "assistant", "content": "...", "ts": "..."},
        ],
        "tags":        ["sales", "netherlands"],
        "score":       0.0,                  — engagement/quality score
    }

Usage (from any bot):

    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "bots" / "memory"))
    from memory_store import MemoryStore

    mem = MemoryStore()
    mem.remember(entity_id="lead_abc123", key="industry", value="SaaS")
    mem.append_conversation("lead_abc123", role="user", content="I'm interested")
    history = mem.get_conversation("lead_abc123")
    facts   = mem.get_facts("lead_abc123")
    similar = mem.search("SaaS Netherlands")   # keyword search across all entities

Config env vars:
    MEMORY_MAX_CONVERSATION — max conversation turns kept per entity (default: 50)
    MEMORY_MAX_FACTS        — max facts kept per entity (default: 100)
"""
import json
import logging
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

logger = logging.getLogger("memory_store")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
MEMORY_DIR = AI_HOME / "state" / "memory"
INDEX_FILE = MEMORY_DIR / "_index.json"

MAX_CONVERSATION = int(os.environ.get("MEMORY_MAX_CONVERSATION", "50"))
MAX_FACTS = int(os.environ.get("MEMORY_MAX_FACTS", "100"))
AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

# Maximum turns to keep in memory before trimming (oldest turns removed first).
# Increase or set to 0 to keep unlimited history.
_DEFAULT_MAX_TURNS = int(os.environ.get("MEMORY_MAX_TURNS", "50"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MemoryStore:
    """Persistent per-entity memory store for AI agents.

    All methods are synchronous and file-based (safe for concurrent use
    through simple file writes; no locking needed for single-process bots).
    """

    def __init__(self) -> None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _entity_path(self, entity_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in entity_id)
        return MEMORY_DIR / f"{safe_id}.json"

    def _load_entity(self, entity_id: str) -> dict:
        path = self._entity_path(entity_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return {
            "entity_id": entity_id,
            "entity_type": "unknown",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "facts": [],
            "conversation": [],
            "tags": [],
            "score": 0.0,
        }

    def _save_entity(self, entity: dict) -> None:
        entity["updated_at"] = _now_iso()
        path = self._entity_path(entity["entity_id"])
        path.write_text(json.dumps(entity, indent=2))
        self._update_index(entity)

    def _load_index(self) -> dict:
        if INDEX_FILE.exists():
            try:
                return json.loads(INDEX_FILE.read_text())
            except Exception:
                pass
        return {"entities": {}}

    def _update_index(self, entity: dict) -> None:
        index = self._load_index()
        index["entities"][entity["entity_id"]] = {
            "entity_type": entity.get("entity_type", "unknown"),
            "updated_at": entity.get("updated_at", ""),
            "tags": entity.get("tags", []),
            "score": entity.get("score", 0.0),
            "fact_count": len(entity.get("facts", [])),
            "conversation_turns": len(entity.get("conversation", [])),
        }
        INDEX_FILE.write_text(json.dumps(index, indent=2))

    # ── Public API ────────────────────────────────────────────────────────────

    def remember(
        self,
        entity_id: str,
        key: str,
        value: str,
        entity_type: str = "unknown",
        tags: Optional[list] = None,
    ) -> None:
        """Store or update a fact about an entity.

        Args:
            entity_id:   Unique identifier for the entity (e.g. lead ID).
            key:         Fact key / label (e.g. "industry", "budget", "pain_point").
            value:       Fact value.
            entity_type: Optional entity category ("lead", "customer", etc.).
            tags:        Optional tags to attach to the entity.
        """
        entity = self._load_entity(entity_id)
        if entity_type != "unknown":
            entity["entity_type"] = entity_type
        if tags:
            for t in tags:
                if t not in entity["tags"]:
                    entity["tags"].append(t)

        # Update existing fact or append new
        for fact in entity["facts"]:
            if fact.get("key") == key:
                fact["value"] = value
                fact["ts"] = _now_iso()
                self._save_entity(entity)
                return

        entity["facts"].append({"key": key, "value": value, "ts": _now_iso()})
        # Trim oldest facts if over limit
        if len(entity["facts"]) > MAX_FACTS:
            entity["facts"] = entity["facts"][-MAX_FACTS:]

        self._save_entity(entity)
        logger.debug("memory_store: remembered [%s] %s=%s", entity_id, key, value[:40])

    def get_facts(self, entity_id: str) -> list:
        """Return all facts stored about an entity as a list of {key, value, ts} dicts."""
        return self._load_entity(entity_id).get("facts", [])

    def get_fact(self, entity_id: str, key: str) -> Optional[str]:
        """Return the value of a specific fact, or None if not found."""
        for fact in self.get_facts(entity_id):
            if fact.get("key") == key:
                return fact.get("value")
        return None

    def append_conversation(
        self,
        entity_id: str,
        role: str,
        content: str,
        entity_type: str = "unknown",
    ) -> None:
        """Append a message to the entity's conversation history.

        Args:
            entity_id:   Entity identifier.
            role:        "user" | "assistant" | "system".
            content:     Message text.
            entity_type: Optional entity category.
        """
        entity = self._load_entity(entity_id)
        if entity_type != "unknown":
            entity["entity_type"] = entity_type

        entity["conversation"].append({
            "role": role,
            "content": content,
            "ts": _now_iso(),
        })
        # Keep conversation within limit (trim oldest turns)
        if len(entity["conversation"]) > MAX_CONVERSATION:
            entity["conversation"] = entity["conversation"][-MAX_CONVERSATION:]

        self._save_entity(entity)

    def get_conversation(self, entity_id: str, last_n: int = 20) -> list:
        """Return the last N conversation turns for an entity.

        Returns a list of {role, content} dicts (without ts) compatible with
        the OpenAI / Anthropic messages format.
        """
        turns = self._load_entity(entity_id).get("conversation", [])
        return [{"role": t["role"], "content": t["content"]} for t in turns[-last_n:]]

    def get_conversation_summary(self, entity_id: str) -> str:
        """Return a plain-text summary of the conversation history."""
        turns = self._load_entity(entity_id).get("conversation", [])
        if not turns:
            return "(no conversation history)"
        lines = []
        for t in turns[-10:]:
            role = t.get("role", "?").capitalize()
            content = t.get("content", "")[:200]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def update_score(self, entity_id: str, delta: float) -> None:
        """Adjust the engagement score for an entity (e.g. +1 on reply, -0.5 on ignore)."""
        entity = self._load_entity(entity_id)
        entity["score"] = round(entity.get("score", 0.0) + delta, 3)
        self._save_entity(entity)

    def get_score(self, entity_id: str) -> float:
        """Return the current engagement score for an entity."""
        return self._load_entity(entity_id).get("score", 0.0)

    def set_entity_type(self, entity_id: str, entity_type: str) -> None:
        """Set or update the entity type for an existing entity."""
        entity = self._load_entity(entity_id)
        entity["entity_type"] = entity_type
        self._save_entity(entity)

    def search(self, query: str, entity_type: Optional[str] = None, limit: int = 10) -> list:
        """Keyword search across all stored entity memories.

        Searches entity IDs, tags, fact keys/values, and conversation content.
        Returns a list of matching entity dicts ordered by score (descending).

        Args:
            query:       Space-separated keywords to search for.
            entity_type: Optional filter (e.g. "lead", "customer").
            limit:       Max results to return.
        """
        keywords = [kw.lower() for kw in query.split() if kw]
        index = self._load_index()
        matches = []

        for entity_id, meta in index.get("entities", {}).items():
            if entity_type and meta.get("entity_type") != entity_type:
                continue

            # Build a searchable text blob from the index entry
            search_text = (
                entity_id
                + " "
                + " ".join(meta.get("tags", []))
            ).lower()

            if any(kw in search_text for kw in keywords):
                entity = self._load_entity(entity_id)
                matches.append(entity)
                continue

            # Deeper search in facts and conversation (only if index miss)
            entity = self._load_entity(entity_id)
            fact_text = " ".join(
                f"{f.get('key','')} {f.get('value','')}" for f in entity.get("facts", [])
            ).lower()
            conv_text = " ".join(
                t.get("content", "") for t in entity.get("conversation", [])
            ).lower()
            combined = fact_text + " " + conv_text

            if any(kw in combined for kw in keywords):
                matches.append(entity)

        # Sort by score descending, then updated_at descending
        matches.sort(key=lambda e: (e.get("score", 0.0), e.get("updated_at", "")), reverse=True)
        return matches[:limit]

    def list_entities(self, entity_type: Optional[str] = None) -> list:
        """Return a list of all entity IDs (optionally filtered by type)."""
        index = self._load_index()
        result = []
        for eid, meta in index.get("entities", {}).items():
            if entity_type is None or meta.get("entity_type") == entity_type:
                result.append(eid)
        return result

    def delete_entity(self, entity_id: str) -> bool:
        """Delete all memory for an entity. Returns True if it existed."""
        path = self._entity_path(entity_id)
        if path.exists():
            path.unlink()
            index = self._load_index()
            index["entities"].pop(entity_id, None)
            INDEX_FILE.write_text(json.dumps(index, indent=2))
            return True
        return False

    def facts_as_context(self, entity_id: str) -> str:
        """Format stored facts as a compact context string for injecting into prompts."""
        facts = self.get_facts(entity_id)
        if not facts:
            return ""
        lines = [f"Known about {entity_id}:"]
        for f in facts:
            lines.append(f"  {f.get('key', '?')}: {f.get('value', '')}")
        return "\n".join(lines)
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

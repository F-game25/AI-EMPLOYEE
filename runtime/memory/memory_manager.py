"""MemoryManager — unified entry point for all 14 memory types (Phase 2E).

Routing table
-------------
session        → short_term_cache (TTL-based)
long_term      → vector_store (semantic)
project        → vault.py markdown store (fallback: JSON file)
company        → strategy_store (goal_type=company)
skill          → strategy_store (goal_type=skill)
tool_history   → JSON persistence (state/memory_tool_history.json)
research       → vector_store (memory_type=research)
financial      → strategy_store (goal_type=financial)
failure        → strategy_store (goal_type=failure)
decision       → vector_store (memory_type=decision)
preference     → JSON persistence (state/memory_preference.json)
knowledge_graph→ state/knowledge_store.json (read) + vector_store write
structured_db  → state/audit.db (SQLite, read-only count; writes via audit)
event_timeline → state/bus.jsonl (append read; write via bus)

Usage::

    from memory.memory_manager import get_memory_manager

    mgr = get_memory_manager()
    mid = mgr.store("The user prefers concise replies", "preference")
    results = mgr.retrieve("user preferences", memory_type="preference")
    print(mgr.stats())
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("memory_manager")

# ── helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_dir() -> Path:
    state = os.getenv("STATE_DIR")
    if state:
        return Path(state)
    from core.state_paths import canonical_state_dir
    return canonical_state_dir()


# ── JSON-file fallback store (for types without a dedicated backend) ──────────

class _JsonStore:
    """Simple file-backed dict store with thread safety."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def put(self, mid: str, content: str, metadata: dict) -> None:
        with self._lock:
            data = self._read()
            data[mid] = {"id": mid, "content": content, "metadata": metadata, "ts": _ts()}
            self._write(data)

    def search(self, query: str, top_k: int) -> list[dict]:
        tokens = set(query.lower().split())
        with self._lock:
            data = self._read()
        results = []
        for mid, entry in data.items():
            text = (entry.get("content") or "").lower()
            score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
            if score > 0:
                results.append({
                    "id": mid,
                    "content": entry.get("content", ""),
                    "metadata": entry.get("metadata", {}),
                    "_score": round(score, 4),
                    "_source": "json_store",
                })
        return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]

    def delete(self, mid: str) -> bool:
        with self._lock:
            data = self._read()
            existed = mid in data
            data.pop(mid, None)
            if existed:
                self._write(data)
            return existed

    def clear(self) -> int:
        with self._lock:
            data = self._read()
            count = len(data)
            self._write({})
            return count

    def count(self) -> int:
        with self._lock:
            return len(self._read())


# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    """Unified entry point for all 14 memory types.

    Routes to the correct store based on memory_type.
    Falls back gracefully when stores are unavailable.
    """

    TYPES = frozenset({
        "session", "long_term", "project", "company", "skill",
        "tool_history", "research", "financial", "failure", "decision",
        "preference", "knowledge_graph", "structured_db", "event_timeline",
    })

    # Types routed to vector store with their metadata tag
    _VECTOR_TYPES = {"long_term", "research", "decision", "knowledge_graph"}

    # Types routed to strategy store with their goal_type label
    _STRATEGY_TYPES = {
        "company": "company",
        "skill": "skill",
        "financial": "financial",
        "failure": "failure",
    }

    # Types backed by a JSON file
    _JSON_TYPES = {"tool_history", "preference"}

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or _state_dir()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

        # Lazy-init stores — failures are contained per store
        self._vs = None          # VectorStore
        self._cache = None       # ShortTermCache
        self._ss = None          # StrategyStore
        self._unified = None     # UnifiedMemoryStore
        self._service = None     # MemoryService
        self._json_stores: dict[str, _JsonStore] = {}

        self._init_stores()

    def _init_stores(self) -> None:
        try:
            from memory.vector_store import get_vector_store
            self._vs = get_vector_store()
        except Exception as e:
            logger.warning("VectorStore unavailable: %s", e)

        try:
            from memory.short_term_cache import get_short_term_cache
            self._cache = get_short_term_cache()
        except Exception as e:
            logger.warning("ShortTermCache unavailable: %s", e)

        try:
            from memory.strategy_store import get_strategy_store
            self._ss = get_strategy_store()
        except Exception as e:
            logger.warning("StrategyStore unavailable: %s", e)

        try:
            from memory.service import MemoryService
            from memory.unified_store import UnifiedMemoryStore
            self._unified = UnifiedMemoryStore(
                path=self._state_dir / "memory" / "unified_memory.json"
            )
            self._service = MemoryService(
                store=self._unified,
                vector_store=self._vs,
                cache=self._cache,
                strategy_store=self._ss,
            )
        except Exception as e:
            logger.warning("Unified memory service unavailable: %s", e)

        for mtype in self._JSON_TYPES:
            self._json_stores[mtype] = _JsonStore(
                self._state_dir / f"memory_{mtype}.json"
            )

    # ── Internal routing helpers ───────────────────────────────────────────────

    def _make_id(self, memory_type: str) -> str:
        return f"{memory_type}:{uuid.uuid4().hex[:12]}"

    def _store_unified(self, mid: str, content: str, memory_type: str, metadata: dict) -> None:
        if self._service is None:
            return
        base_importance = 0.6 if memory_type in self._VECTOR_TYPES else 0.3
        importance = metadata.get("importance", base_importance)
        extra = {
            **metadata,
            "manager_memory_type": memory_type,
            "manager_id": mid,
        }
        self._service.remember(
            content,
            key=mid,
            memory_type=memory_type,
            source=metadata.get("source", "memory_manager"),
            importance=importance,
            agent=metadata.get("agent", "memory_manager"),
            project_id=metadata.get("project_id"),
            session_id=metadata.get("session_id"),
            task_id=metadata.get("task_id"),
            tags=metadata.get("tags"),
            topic=metadata.get("topic"),
            summary=metadata.get("summary"),
            verified=bool(metadata.get("verified", False)),
            sensitive=bool(metadata.get("sensitive", False)),
            visibility=metadata.get("visibility", "private"),
            extra=extra,
        )

    def _store_vector(self, mid: str, content: str, memory_type: str, metadata: dict) -> None:
        if self._vs is None:
            return
        meta = {**metadata, "memory_type": memory_type, "manager_id": mid}
        self._vs.store(mid, content, metadata=meta, importance=metadata.get("importance", 0.6))

    def _store_session(self, mid: str, content: str, metadata: dict) -> None:
        if self._cache is None:
            return
        ttl = float(metadata.get("ttl", 1800))
        self._cache.set(mid, {"content": content, "metadata": metadata, "id": mid}, ttl=ttl)

    def _store_strategy(self, mid: str, content: str, goal_type: str, metadata: dict) -> None:
        if self._ss is None:
            return
        self._ss.record(
            goal_type=goal_type,
            agent=metadata.get("agent", "memory_manager"),
            config={"content": content[:500], "manager_id": mid, **metadata},
            outcome_score=float(metadata.get("importance", 0.6)),
            notes=content[:200],
        )

    def _store_project(self, mid: str, content: str, metadata: dict) -> None:
        """Write project memory to vault (markdown) with JSON fallback."""
        try:
            from memory.vault import Vault
            vault_root = Path.home() / ".ai-employee" / "vault"
            v = Vault(vault_root)
            v.create(
                title=metadata.get("title", mid),
                folder="projects",
                body=content,
                tags=metadata.get("tags", ["memory_manager"]),
            )
        except Exception:
            # Fallback: persist to JSON store
            store = self._json_stores.setdefault(
                "project", _JsonStore(self._state_dir / "memory_project.json")
            )
            store.put(mid, content, metadata)

    def _store_event_timeline(self, mid: str, content: str, metadata: dict) -> None:
        """Append to state/bus.jsonl as a memory event."""
        bus_path = self._state_dir / "bus.jsonl"
        entry = json.dumps({
            "channel": "memory",
            "event": "timeline_store",
            "id": mid,
            "content": content[:500],
            "metadata": metadata,
            "ts": _ts(),
        }, default=str)
        try:
            with self._lock:
                with open(bus_path, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
        except Exception as e:
            logger.warning("event_timeline write failed: %s", e)

    # ── Public API ────────────────────────────────────────────────────────────

    def store(self, content: str, memory_type: str, metadata: dict | None = None) -> str:
        """Store content. Returns memory_id."""
        metadata = dict(metadata or {})
        if memory_type not in self.TYPES:
            logger.warning("Unknown memory_type %r — defaulting to long_term", memory_type)
            memory_type = "long_term"

        mid = self._make_id(memory_type)

        try:
            self._store_unified(mid, content, memory_type, metadata)

            if memory_type == "session":
                self._store_session(mid, content, metadata)

            elif memory_type in self._VECTOR_TYPES:
                self._store_vector(mid, content, memory_type, metadata)

            elif memory_type in self._STRATEGY_TYPES:
                self._store_strategy(mid, content, self._STRATEGY_TYPES[memory_type], metadata)

            elif memory_type in self._JSON_TYPES:
                self._json_stores[memory_type].put(mid, content, metadata)

            elif memory_type == "project":
                self._store_project(mid, content, metadata)

            elif memory_type == "event_timeline":
                self._store_event_timeline(mid, content, metadata)

            elif memory_type == "structured_db":
                # structured_db is read-only via audit.db — direct writes not supported
                logger.info("structured_db is read-only via audit trail; skipping store for %s", mid)

        except Exception as e:
            logger.error("store failed for type=%s: %s", memory_type, e)

        return mid

    def retrieve(self, query: str, memory_type: str | None = None, top_k: int = 10) -> list[dict]:
        """Retrieve relevant memories. memory_type=None searches all types."""
        types_to_search = [memory_type] if memory_type else list(self.TYPES)
        results: list[dict] = []
        seen_ids: set[str] = set()

        for mtype in types_to_search:
            try:
                hits = self._retrieve_type(query, mtype, top_k)
                for h in hits:
                    mid = h.get("id") or h.get("key", "")
                    if mid not in seen_ids:
                        h.setdefault("memory_type", mtype)
                        results.append(h)
                        if mid:
                            seen_ids.add(mid)
            except Exception as e:
                logger.warning("retrieve failed for type=%s: %s", mtype, e)

        results.sort(key=lambda x: float(x.get("_score", 0.0)), reverse=True)
        return results[:top_k]

    def _retrieve_type(self, query: str, memory_type: str, top_k: int) -> list[dict]:
        if memory_type == "session":
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_session(query, top_k),
                top_k,
            )

        if memory_type in self._VECTOR_TYPES:
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_vector(query, memory_type, top_k),
                top_k,
            )

        if memory_type in self._STRATEGY_TYPES:
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k)
                + self._search_strategy(query, self._STRATEGY_TYPES[memory_type], top_k),
                top_k,
            )

        if memory_type in self._JSON_TYPES:
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._json_stores[memory_type].search(query, top_k),
                top_k,
            )

        if memory_type == "project":
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_project(query, top_k),
                top_k,
            )

        if memory_type == "knowledge_graph":
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_knowledge_graph(query, top_k),
                top_k,
            )

        if memory_type == "event_timeline":
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_event_timeline(query, top_k),
                top_k,
            )

        if memory_type == "structured_db":
            return self._dedupe_results(
                self._search_unified(query, memory_type, top_k) + self._search_structured_db(query, top_k),
                top_k,
            )

        return []

    def _search_unified(self, query: str, memory_type: str, top_k: int) -> list[dict]:
        if self._service is None:
            return []
        hits = self._service.retrieve(query, memory_type=memory_type, top_k=top_k)
        results = []
        for h in hits:
            metadata = h.get("metadata", {})
            mid = h.get("id") or h.get("key") or metadata.get("manager_id", "")
            results.append({
                "id": mid,
                "content": h.get("text", ""),
                "metadata": metadata,
                "record": h.get("record"),
                "_score": h.get("_score", 0.0),
                "_source": "unified_memory",
            })
        return results

    @staticmethod
    def _dedupe_results(results: list[dict], top_k: int) -> list[dict]:
        by_id: dict[str, dict] = {}
        anonymous: list[dict] = []
        for row in results:
            mid = row.get("id") or row.get("key")
            if not mid:
                anonymous.append(row)
                continue
            existing = by_id.get(mid)
            if existing is None:
                by_id[mid] = row
                continue
            current_score = float(row.get("_score", 0.0))
            existing_score = float(existing.get("_score", 0.0))
            if row.get("_source") == "unified_memory":
                row["_score"] = max(current_score, existing_score)
                by_id[mid] = row
            elif existing.get("_source") != "unified_memory" and current_score > existing_score:
                by_id[mid] = row

        merged = list(by_id.values()) + anonymous
        merged.sort(key=lambda x: float(x.get("_score", 0.0)), reverse=True)
        return merged[:top_k]

    def _search_session(self, query: str, top_k: int) -> list[dict]:
        if self._cache is None:
            return []
        tokens = set(query.lower().split())
        results = []
        for k, val in self._cache.snapshot().items():
            if not isinstance(val, dict):
                continue
            text = (val.get("content") or "").lower()
            score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
            if score > 0:
                results.append({
                    "id": k, "content": val.get("content", ""),
                    "metadata": val.get("metadata", {}),
                    "_score": round(score * 0.5, 4), "_source": "session_cache",
                })
        return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]

    def _search_vector(self, query: str, memory_type: str, top_k: int) -> list[dict]:
        if self._vs is None:
            return []
        hits = self._vs.search(query, top_k=top_k, memory_type=memory_type)
        return [
            {"id": h.get("key", ""), "content": h.get("text", ""),
             "metadata": h.get("metadata", {}), "_score": h.get("_score", 0.0),
             "_source": "vector_store"}
            for h in hits
        ]

    def _search_strategy(self, query: str, goal_type: str, top_k: int) -> list[dict]:
        if self._ss is None:
            return []
        strategies = self._ss.get_best_strategy(goal_type, top_n=top_k)
        tokens = set(query.lower().split())
        results = []
        for s in strategies:
            text = (s.get("notes") or "").lower() + " " + str(s.get("config", {})).lower()
            score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
            results.append({
                "id": s.get("strategy_id", ""),
                "content": s.get("notes", ""),
                "metadata": {k: v for k, v in s.items() if k not in ("notes",)},
                "_score": max(round(score, 4), s.get("outcome_score", 0.0) * 0.3),
                "_source": "strategy_store",
            })
        return results

    def _search_project(self, query: str, top_k: int) -> list[dict]:
        # Try vault first
        try:
            from memory.vault import Vault
            vault_root = Path.home() / ".ai-employee" / "vault"
            v = Vault(vault_root)
            tokens = set(query.lower().split())
            results = []
            for ref in v.list_notes(folder="projects"):
                note = v.get(ref.id)
                if not note:
                    continue
                text = (note.body or "").lower()
                score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
                if score > 0:
                    results.append({
                        "id": ref.id, "content": note.body[:500],
                        "metadata": note.frontmatter,
                        "_score": round(score, 4), "_source": "vault",
                    })
            if results:
                return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]
        except Exception:
            pass
        # Fallback to JSON store
        store = self._json_stores.get(
            "project", _JsonStore(self._state_dir / "memory_project.json")
        )
        return store.search(query, top_k)

    def _search_knowledge_graph(self, query: str, top_k: int) -> list[dict]:
        ks_path = self._state_dir / "knowledge_store.json"
        try:
            raw = json.loads(ks_path.read_text(encoding="utf-8"))
            nodes = raw if isinstance(raw, list) else raw.get("nodes", raw.get("entries", []))
            tokens = set(query.lower().split())
            results = []
            for node in nodes:
                text = str(node).lower()
                score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
                if score > 0:
                    results.append({
                        "id": node.get("id", node.get("key", str(id(node)))),
                        "content": node.get("content", node.get("text", str(node)))[:400],
                        "metadata": {k: v for k, v in node.items() if k not in ("content", "text")},
                        "_score": round(score, 4), "_source": "knowledge_store",
                    })
            return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]
        except Exception as e:
            logger.debug("knowledge_graph search failed: %s", e)
            return []

    def _search_event_timeline(self, query: str, top_k: int) -> list[dict]:
        bus_path = self._state_dir / "bus.jsonl"
        tokens = set(query.lower().split())
        results = []
        try:
            lines = bus_path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-2000:]):  # scan last 2000 events
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                text = str(entry).lower()
                score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
                if score > 0:
                    results.append({
                        "id": entry.get("id", entry.get("ts", "")),
                        "content": entry.get("content", str(entry))[:400],
                        "metadata": entry,
                        "_score": round(score, 4), "_source": "bus_jsonl",
                    })
                if len(results) >= top_k * 3:
                    break
        except Exception as e:
            logger.debug("event_timeline search failed: %s", e)
        return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]

    def _search_structured_db(self, query: str, top_k: int) -> list[dict]:
        db_path = self._state_dir / "audit.db"
        if not db_path.exists():
            return []
        tokens = set(query.lower().split())
        results = []
        try:
            con = sqlite3.connect(str(db_path), timeout=3)
            con.row_factory = sqlite3.Row
            cur = con.execute("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT 500")
            for row in cur:
                text = " ".join(str(v) for v in dict(row).values()).lower()
                score = sum(1 for t in tokens if len(t) > 2 and t in text) / max(len(tokens), 1)
                if score > 0:
                    results.append({
                        "id": str(dict(row).get("id", "")),
                        "content": text[:400],
                        "metadata": dict(row),
                        "_score": round(score, 4), "_source": "audit_db",
                    })
            con.close()
        except Exception as e:
            logger.debug("structured_db search failed: %s", e)
        return sorted(results, key=lambda x: x["_score"], reverse=True)[:top_k]

    # ── Stats ──────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return counts per type and totals."""
        counts: dict[str, int] = {}

        # session
        try:
            counts["session"] = self._cache.size() if self._cache else 0
        except Exception:
            counts["session"] = 0

        # vector-backed types
        for mtype in self._VECTOR_TYPES:
            try:
                counts[mtype] = self._vs.count(memory_type=mtype) if self._vs else 0
            except Exception:
                counts[mtype] = 0

        # strategy-backed types — count by goal_type
        for mtype, goal_type in self._STRATEGY_TYPES.items():
            try:
                if self._ss:
                    all_s = self._ss.all_strategies()
                    counts[mtype] = sum(1 for s in all_s if s.get("goal_type") == goal_type)
                else:
                    counts[mtype] = 0
            except Exception:
                counts[mtype] = 0

        # JSON-backed types
        for mtype in self._JSON_TYPES:
            try:
                counts[mtype] = self._json_stores[mtype].count()
            except Exception:
                counts[mtype] = 0

        # project — vault or JSON fallback
        try:
            from memory.vault import Vault
            v = Vault(Path.home() / ".ai-employee" / "vault")
            counts["project"] = len(v.list_notes(folder="projects"))
        except Exception:
            try:
                store = self._json_stores.get("project", _JsonStore(self._state_dir / "memory_project.json"))
                counts["project"] = store.count()
            except Exception:
                counts["project"] = 0

        # knowledge_graph
        try:
            ks_path = self._state_dir / "knowledge_store.json"
            raw = json.loads(ks_path.read_text(encoding="utf-8"))
            nodes = raw if isinstance(raw, list) else raw.get("nodes", raw.get("entries", []))
            counts["knowledge_graph"] = len(nodes) if isinstance(nodes, list) else 0
        except Exception:
            counts["knowledge_graph"] = 0

        # structured_db — row count from audit.db
        try:
            db_path = self._state_dir / "audit.db"
            if db_path.exists():
                con = sqlite3.connect(str(db_path), timeout=2)
                row = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()
                con.close()
                counts["structured_db"] = row[0] if row else 0
            else:
                counts["structured_db"] = 0
        except Exception:
            counts["structured_db"] = 0

        # event_timeline — line count in bus.jsonl
        try:
            bus_path = self._state_dir / "bus.jsonl"
            counts["event_timeline"] = sum(1 for _ in bus_path.open(encoding="utf-8")) if bus_path.exists() else 0
        except Exception:
            counts["event_timeline"] = 0

        canonical_counts: dict[str, int] = {}
        if self._unified is not None:
            for mtype in self.TYPES:
                try:
                    canonical_counts[mtype] = self._unified.count(memory_type=mtype)
                    counts[mtype] = max(counts.get(mtype, 0), canonical_counts[mtype])
                except Exception:
                    canonical_counts[mtype] = 0

        vector_indexed = sum(counts.get(t, 0) for t in self._VECTOR_TYPES)
        total = sum(counts.values())

        return {
            "types": counts,
            "total": total,
            "vector_indexed": vector_indexed,
            "canonical_total": sum(canonical_counts.values()),
            "ts": _ts(),
        }

    # ── Delete / clear ────────────────────────────────────────────────────────

    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by id. Tries all applicable stores."""
        # Infer type from prefix
        mtype = memory_id.split(":")[0] if ":" in memory_id else None
        deleted = False
        canonical_failed = False

        if self._unified is not None:
            try:
                deleted = self._unified.delete(memory_id) or deleted
            except Exception as exc:
                canonical_failed = True
                logger.warning("canonical memory delete failed for %s: %s", memory_id, exc)

        if mtype in self._VECTOR_TYPES and self._vs:
            try:
                deleted = self._vs.delete(memory_id) or deleted
            except Exception:
                pass

        if mtype in self._JSON_TYPES and mtype in self._json_stores:
            try:
                deleted = self._json_stores[mtype].delete(memory_id) or deleted
            except Exception:
                pass

        if mtype == "session" and self._cache:
            try:
                deleted = self._cache.delete(memory_id) or deleted
            except Exception:
                pass

        if mtype == "project":
            try:
                from memory.vault import Vault
                v = Vault(Path.home() / ".ai-employee" / "vault")
                v.delete(memory_id)
                deleted = True
            except Exception:
                pass

        # Canonical store is the source of truth: never report success if its delete
        # errored, even when a secondary delete succeeded (the record stays retrievable).
        if canonical_failed:
            return False
        return deleted

    def clear_type(self, memory_type: str) -> int:
        """Clear all memories of a type. Returns count deleted."""
        if memory_type not in self.TYPES:
            raise ValueError(f"Unknown memory_type: {memory_type!r}")

        if memory_type == "session":
            try:
                return self._cache.flush() if self._cache else 0
            except Exception:
                return 0

        if memory_type in self._JSON_TYPES:
            try:
                return self._json_stores[memory_type].clear()
            except Exception:
                return 0

        if memory_type == "project":
            store = self._json_stores.get("project", _JsonStore(self._state_dir / "memory_project.json"))
            return store.clear()

        # Vector and strategy types: count first, then drop
        if memory_type in self._VECTOR_TYPES and self._vs:
            try:
                # VectorStore doesn't support bulk-delete-by-type; return count and warn
                count = self._vs.count(memory_type=memory_type)
                logger.warning("clear_type(%s): vector store bulk-delete not supported; count=%d", memory_type, count)
                return count
            except Exception:
                return 0

        logger.warning("clear_type(%s): no clear operation defined for this type", memory_type)
        return 0


# ── Singleton factory ─────────────────────────────────────────────────────────

_instance: MemoryManager | None = None
_instance_lock = threading.Lock()


def get_memory_manager(state_dir: Path | None = None) -> MemoryManager:
    """Return the process-wide MemoryManager singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MemoryManager(state_dir=state_dir)
    return _instance


# ── FastAPI router ────────────────────────────────────────────────────────────

try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel

    router = APIRouter(prefix="/api/memory", tags=["memory"])

    class StoreRequest(BaseModel):
        content: str
        memory_type: str
        metadata: dict = {}

    @router.get("/stats")
    def api_stats() -> dict:
        return get_memory_manager().stats()

    @router.post("/store")
    def api_store(req: StoreRequest) -> dict:
        if req.memory_type not in MemoryManager.TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown memory_type: {req.memory_type!r}")
        mid = get_memory_manager().store(req.content, req.memory_type, req.metadata)
        return {"memory_id": mid, "memory_type": req.memory_type, "ts": _ts()}

    @router.get("/retrieve")
    def api_retrieve(
        query: str = Query(..., description="Search query"),
        memory_type: str | None = Query(None, description="Filter by memory type"),
        top_k: int = Query(10, ge=1, le=100),
    ) -> dict:
        results = get_memory_manager().retrieve(query, memory_type=memory_type, top_k=top_k)
        return {"results": results, "count": len(results), "query": query}

except ImportError:
    router = None  # type: ignore[assignment]
    logger.debug("FastAPI not available — HTTP router not registered")

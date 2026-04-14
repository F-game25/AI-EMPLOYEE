"""Persistent topic/context memory used by planning and routing."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_STORE = {
    "topics": {
        "ecommerce": [],
        "marketing": [],
        "lead_generation": [],
    },
    "insights": [],
    "strategies": [],
    "user_profile": {
        "goals": [],
        "business_type": "",
        "preferences": [],
        "updated_at": None,
    },
}


class KnowledgeStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self._default_path()
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    @staticmethod
    def _default_path() -> Path:
        home = os.getenv("AI_HOME")
        if home:
            base = Path(home)
        else:
            base = Path(__file__).resolve().parents[2]
        return base / "state" / "knowledge_store.json"

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return dict(_DEFAULT_STORE)
            merged = dict(_DEFAULT_STORE)
            merged.update(payload)
            merged["topics"] = dict(_DEFAULT_STORE["topics"]) | dict(merged.get("topics", {}))
            merged["user_profile"] = dict(_DEFAULT_STORE["user_profile"]) | dict(merged.get("user_profile", {}))
            return merged
        except Exception:
            self._write(dict(_DEFAULT_STORE))
            return dict(_DEFAULT_STORE)

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save(self) -> dict[str, Any]:
        with self._lock:
            self._write(self._state)
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def add_knowledge(self, topic: str, content: Any) -> dict[str, Any]:
        topic_key = (topic or "general").strip().lower()
        with self._lock:
            topics = self._state.setdefault("topics", {})
            topic_items = topics.setdefault(topic_key, [])
            topic_items.append({
                "content": content,
                "stored_at": self._ts(),
            })
            self._state.setdefault("insights", []).append(
                {"topic": topic_key, "content": content, "stored_at": self._ts()}
            )
            self._write(self._state)
            return {"topic": topic_key, "entries": len(topic_items)}

    def search_knowledge(self, query: str) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return []
        with self._lock:
            hits: list[dict[str, Any]] = []
            for topic, entries in self._state.get("topics", {}).items():
                for item in entries:
                    blob = json.dumps(item, ensure_ascii=False).lower()
                    if q in topic or q in blob:
                        hits.append({"topic": topic, **item})
            for item in self._state.get("insights", []):
                blob = json.dumps(item, ensure_ascii=False).lower()
                if q in blob:
                    hits.append(item)
            return hits[:20]

    def get_relevant_context(self, task: str) -> str:
        task_text = (task or "").strip().lower()
        if not task_text:
            return ""
        with self._lock:
            relevant: list[str] = []
            for topic, entries in self._state.get("topics", {}).items():
                if topic in task_text:
                    for item in entries[-3:]:
                        relevant.append(f"[{topic}] {item.get('content')}")
            for item in self._state.get("insights", [])[-20:]:
                blob = json.dumps(item, ensure_ascii=False).lower()
                if any(token in blob for token in task_text.split()[:8]):
                    relevant.append(str(item.get("content", "")))
            return "\n".join(relevant[:8])

    def update_user_profile(
        self,
        *,
        goals: list[str] | None = None,
        business_type: str | None = None,
        preferences: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            profile = self._state.setdefault("user_profile", dict(_DEFAULT_STORE["user_profile"]))
            if goals:
                profile["goals"] = list(dict.fromkeys([*(profile.get("goals", [])), *goals]))[-30:]
            if business_type:
                profile["business_type"] = business_type
            if preferences:
                profile["preferences"] = list(dict.fromkeys([*(profile.get("preferences", [])), *preferences]))[-30:]
            profile["updated_at"] = self._ts()
            self._write(self._state)
            return dict(profile)

    def learn_from_conversation(self, text: str) -> dict[str, Any]:
        msg = (text or "").strip()
        if not msg:
            return {}
        lower = msg.lower()
        goals = []
        prefs = []
        business_type = ""

        if any(k in lower for k in ("goal", "need", "want", "plan", "strategy")):
            goals.append(msg[:160])
        match = re.search(r"(?:business|company|store|brand)\s*(?:is|type|:)\s*([a-z0-9\-\s]+)", lower)
        if match:
            business_type = match.group(1).strip()[:80]
        for key in ("budget", "tone", "audience", "industry", "market", "timeline"):
            if key in lower:
                prefs.append(f"{key}:{msg[:120]}")

        return self.update_user_profile(goals=goals, business_type=business_type or None, preferences=prefs)


_instance: KnowledgeStore | None = None
_instance_lock = threading.Lock()


def get_knowledge_store(path: Path | None = None) -> KnowledgeStore:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = KnowledgeStore(path)
        elif path is not None and _instance._path != path:
            _instance = KnowledgeStore(path)
    return _instance

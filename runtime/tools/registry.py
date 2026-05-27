"""Atomic tool registry.

Lightweight in-process registry. Each tool advertises:
``name``, ``description``, ``input_schema``, ``output_schema``, and
``call(input_data) -> dict``.

Also exposes a class-based ``ToolRegistry`` singleton (used by skills and
API routes) that wraps the same underlying ``_REGISTRY`` store and adds
``execute()``, ``list_tools(max_risk)``, and pre-registered default tools.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_REGISTRY: dict[str, dict[str, Any]] = {}


def register_tool(
    *,
    name: str,
    description: str,
    call: Callable[[dict[str, Any]], dict[str, Any]],
    input_schema: Optional[dict[str, Any]] = None,
    output_schema: Optional[dict[str, Any]] = None,
    tags: Optional[list[str]] = None,
) -> None:
    with _LOCK:
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "call": call,
            "input_schema": input_schema or {"type": "object"},
            "output_schema": output_schema or {"type": "object"},
            "tags": list(tags or []),
        }
        logger.debug("tool registered: %s", name)


def list_tools() -> list[dict[str, Any]]:
    with _LOCK:
        return [
            {k: v for k, v in entry.items() if k != "call"}
            for entry in _REGISTRY.values()
        ]


def call_tool(name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        entry = _REGISTRY.get(name)
    if not entry:
        return {"status": "error", "error": f"unknown tool: {name}"}
    try:
        return entry["call"](input_data) or {}
    except Exception as e:
        logger.warning("tool '%s' raised: %s", name, e)
        return {"status": "error", "error": str(e)}


# ── Class-based singleton registry ────────────────────────────────────────────

class ToolRegistry:
    """Singleton class-based tool registry with risk levels and execute()."""

    _instance: "ToolRegistry | None" = None
    _cls_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        with cls._cls_lock:
            if cls._instance is None:
                inst = cls.__new__(cls)
                inst._tools: dict[str, dict[str, Any]] = {}
                inst._register_defaults()
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        # Direct instantiation supported; use get_instance() for the singleton.
        if not hasattr(self, "_tools"):
            self._tools: dict[str, dict[str, Any]] = {}
            self._register_defaults()

    def register(self, name: str, fn: Callable, risk_level: int,
                 description: str, input_schema: dict | None = None) -> None:
        self._tools[name] = {
            "name": name, "fn": fn, "risk_level": risk_level,
            "description": description, "schema": input_schema or {},
        }

    def get(self, name: str) -> dict | None:
        return self._tools.get(name)

    def list_tools(self, max_risk: int = 5) -> list[dict]:
        return [
            {"name": k, "risk_level": v["risk_level"], "description": v["description"]}
            for k, v in self._tools.items() if v["risk_level"] <= max_risk
        ]

    def execute(self, name: str, payload: dict, agent_id: str = "system") -> dict:
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Tool '{name}' not found"}
        try:
            result = tool["fn"](**payload)
            return {"ok": True, "tool": name, "result": result}
        except Exception as e:
            logger.warning("ToolRegistry.execute '%s' raised: %s", name, e)
            return {"ok": False, "tool": name, "error": str(e)}

    def _register_defaults(self) -> None:
        # Risk 0 — read-only
        self.register("web_search", self._web_search, 0, "Search the web")
        self.register("read_file", self._read_file, 0, "Read a file")
        self.register("llm_infer", self._llm_infer, 0, "Run LLM inference")
        self.register("embed_text", self._embed_text, 0, "Embed text to vector")
        self.register("get_memory", self._get_memory, 0, "Retrieve from memory")
        # Risk 1 — local write
        self.register("write_file", self._write_file, 1, "Write a file")
        self.register("create_file", self._create_file, 1, "Create a new file")
        self.register("update_db", self._update_db, 1, "Update database")
        # Risk 3 — external
        self.register("send_email", self._send_email, 3, "Send an email")
        self.register("call_api", self._call_api, 3, "Call an external API")
        self.register("browser_fetch", self._browser_fetch, 3, "Fetch a URL")

    def _web_search(self, query: str, limit: int = 5, **_):
        try:
            from tools.web_research_tool import search
            return search(query, limit)
        except Exception:
            return {"results": [], "stub": True, "query": query}

    def _read_file(self, path: str, **_):
        import os
        if not os.path.exists(path):
            return {"error": "file not found"}
        return {"content": open(path).read()[:10000]}

    def _write_file(self, path: str, content: str, **_):
        import os
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return {"written": len(content), "path": path}

    def _create_file(self, path: str, content: str = "", **_):
        return self._write_file(path, content)

    def _llm_infer(self, prompt: str, model: str = None, max_tokens: int = 500, **_):
        try:
            from core.orchestrator import LLMClient
            return {"output": LLMClient().complete(prompt, max_tokens=max_tokens)}
        except Exception as e:
            return {"error": str(e), "stub": True}

    def _embed_text(self, text: str, **_):
        try:
            from core.embeddings import get_embeddings_manager
            return {"embedding": get_embeddings_manager().embed_text(text)}
        except Exception:
            return {"stub": True, "text_length": len(text)}

    def _get_memory(self, query: str, top_k: int = 5, **_):
        try:
            from memory.memory_router import hybrid_search
            return {"results": hybrid_search(query, top_k=top_k)}
        except Exception:
            return {"results": [], "stub": True}

    def _update_db(self, sql: str, params: list = None, **_):
        return {"stub": True, "sql": sql}

    def _send_email(self, to: str, subject: str, body: str, **_):
        return {"stub": True, "blocked": "Email sending requires HITL approval"}

    def _call_api(self, url: str, method: str = "GET", headers: dict = None,
                  body: dict = None, **_):
        import urllib.request, json as _json
        req = urllib.request.Request(
            url, method=method.upper(),
            headers=headers or {"Content-Type": "application/json"},
        )
        if body:
            req.data = _json.dumps(body).encode()
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"status": r.status, "body": r.read().decode()[:5000]}

    def _browser_fetch(self, url: str, **_):
        return self._call_api(url)


def get_tool_registry() -> ToolRegistry:
    """Return the ToolRegistry singleton (class-based, with execute())."""
    return ToolRegistry.get_instance()


# ── Module-level helpers (backward-compat) ────────────────────────────────────

def _module_get_tool_registry_dict() -> dict[str, dict[str, Any]]:
    """Original dict-returning helper; kept for callers that expect a raw dict."""
    with _LOCK:
        return dict(_REGISTRY)


# Auto-register built-in tools when the package is imported
def _autoregister() -> None:
    try:
        from . import web_research_tool  # noqa: F401
        from . import context_score_tool  # noqa: F401
    except Exception as e:
        logger.debug("tool autoregister partial failure: %s", e)


_autoregister()

"""Centralized LLM routing — single source of truth for which provider+model
each agent / subsystem / task type uses. Read by LLMClient and ai_router.

Routing file schema (state/model-routing.json or ~/.ai-employee/model-routing.json):
{
  "_default": { "provider": "anthropic", "model": "claude-sonnet-4-6" },
  "tasks": {
    "coding":    { "provider": "...", "model": "...", "fallback_provider": "...", "fallback_model": "..." },
    ...
  },
  "agents":     { "<agent_id>": { "provider": "...", "model": "..." } },
  "subsystems": { "ascend-forge": {...}, "blacklight": {...}, "money-mode": {...} }
}

Priority: subsystem > agent > tasks[task_type] > _default > env fallback.
"""
import json
import logging
import os
import threading
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Optional, Tuple

_OLLAMA_REACHABLE: Optional[bool] = None


def _ollama_reachable() -> bool:
    """1s HTTP check to the Ollama tags endpoint. Result cached for the process."""
    global _OLLAMA_REACHABLE
    if _OLLAMA_REACHABLE is not None:
        return _OLLAMA_REACHABLE
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=1) as resp:
            _OLLAMA_REACHABLE = resp.status == 200
    except Exception:
        _OLLAMA_REACHABLE = False
    return _OLLAMA_REACHABLE

_TASK_DEFAULTS = {
    "coding":    {"provider": "nvidia_nim", "model": "qwen/qwen2.5-coder-32b-instruct",        "fallback_provider": "anthropic", "fallback_model": "claude-sonnet-4-6"},
    "reasoning": {"provider": "nvidia_nim", "model": "nvidia/llama-3.3-nemotron-super-49b-v1", "fallback_provider": "anthropic", "fallback_model": "claude-opus-4-7"},
    "creative":  {"provider": "ollama",     "model": "gemma4",                                   "fallback_provider": "anthropic", "fallback_model": "claude-sonnet-4-6"},
    "analytics": {"provider": "anthropic",  "model": "claude-opus-4-7"},
    "bulk":      {"provider": "nvidia_nim", "model": "meta/llama-3.1-8b-instruct",               "fallback_provider": "ollama",    "fallback_model": "llama3.2"},
    "general":   {"provider": "ollama",     "model": "llama3.2",                                 "fallback_provider": "anthropic", "fallback_model": "claude-haiku-4-5-20251001"},
}

_DEFAULT_ROUTING = {
    "_default": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "tasks": _TASK_DEFAULTS,
    "agents": {},
}


class LLMRouter:
    _CANDIDATES = [
        Path(os.path.expanduser('~/.ai-employee/model-routing.json')),
        Path('/home/lf/AI-EMPLOYEE/state/model-routing.json'),
    ]

    def __init__(self):
        self._cache = None
        self._mtime = 0.0
        self._path = self._resolve_path()
        self._lock = threading.RLock()
        self._ensure_defaults()

    def _resolve_path(self) -> Path:
        for p in self._CANDIDATES:
            if p.exists():
                return p
        # Default: persist to ~/.ai-employee since that's what the Node backend writes to
        return self._CANDIDATES[0]

    def _ensure_defaults(self):
        """Write default routing config if no file exists."""
        if not self._path.exists():
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(_DEFAULT_ROUTING, indent=2))
            except Exception:
                pass

    def reload(self) -> dict:
        """Force an immediate config reload from disk regardless of mtime."""
        with self._lock:
            self._mtime = 0.0
            self._cache = None
            cfg = self._load()
            logger.info("LLM routing config reloaded (forced): %s", self._path)
            return cfg

    def _load(self) -> dict:
        with self._lock:
            try:
                mtime = self._path.stat().st_mtime if self._path.exists() else 0
                if self._cache is None or mtime > self._mtime:
                    if self._path.exists():
                        self._cache = json.loads(self._path.read_text())
                        if mtime > self._mtime:
                            logger.info("LLM routing config reloaded from %s", self._path)
                    else:
                        self._cache = {}
                    self._mtime = mtime
            except Exception:
                self._cache = {}
            return self._cache or {}

    def _env_fallback(self) -> Tuple[str, str]:
        backend = os.getenv('LLM_BACKEND', 'anthropic').strip().lower()
        # Local-first auto-switch: if the chosen cloud backend has no API key but
        # Ollama is reachable, fall back to local Ollama instead of failing.
        if backend == 'anthropic' and not os.getenv('ANTHROPIC_API_KEY', '').strip():
            if os.getenv('OLLAMA_HOST') or _ollama_reachable():
                backend = 'ollama'
        elif backend == 'openai' and not os.getenv('OPENAI_API_KEY', '').strip():
            if os.getenv('OLLAMA_HOST') or _ollama_reachable():
                backend = 'ollama'
        models = {
            'anthropic':  os.getenv('ANTHROPIC_MODEL',  'claude-sonnet-4-6'),
            'ollama':     os.getenv('OLLAMA_MODEL',     'llama3.2:latest'),
            'openrouter': os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-coder-v2'),
            'openai':     os.getenv('OPENAI_MODEL',     'gpt-4o'),
        }
        return backend, models.get(backend, 'claude-sonnet-4-6')

    # ── New task-type API ─────────────────────────────────────────────────────

    def get_model_for_task(self, task_type: str) -> dict:
        """Return { provider, model, fallback_provider?, fallback_model? } for a task type.
        Priority: tasks[task_type] in JSON → _TASK_DEFAULTS → _default → env fallback.
        """
        cfg = self._load()
        r = (cfg.get('tasks') or {}).get(task_type)
        if r:
            return dict(r)
        r = _TASK_DEFAULTS.get(task_type)
        if r:
            return dict(r)
        d = cfg.get('_default')
        if d:
            return dict(d)
        provider, model = self._env_fallback()
        return {"provider": provider, "model": model}

    def get_model_for_agent(self, agent_id: str) -> dict:
        """Return { provider, model } for a specific agent ID.
        Falls back to _default and then env fallback.
        """
        cfg = self._load()
        r = (cfg.get('agents') or {}).get(agent_id)
        if r:
            return dict(r)
        d = cfg.get('_default')
        if d:
            return dict(d)
        provider, model = self._env_fallback()
        return {"provider": provider, "model": model}

    def get_all_routing(self) -> dict:
        """Return the full merged routing config (JSON + env defaults)."""
        cfg = self._load()
        merged = dict(_DEFAULT_ROUTING)
        merged.update(cfg)
        # Merge task-level overrides on top of defaults
        merged_tasks = dict(_TASK_DEFAULTS)
        merged_tasks.update(cfg.get('tasks') or {})
        merged['tasks'] = merged_tasks
        return merged

    def set_model_for_task(self, task_type: str, provider: str, model: str) -> None:
        """Persist a task-type routing override to model-routing.json."""
        cfg = self._load()
        cfg.setdefault('tasks', {})[task_type] = {"provider": provider, "model": model}
        self._save(cfg)

    def set_model_for_agent(self, agent_id: str, provider: str, model: str) -> None:
        """Persist an agent-level routing override to model-routing.json."""
        cfg = self._load()
        cfg.setdefault('agents', {})[agent_id] = {"provider": provider, "model": model}
        self._save(cfg)

    # ── Legacy API (kept for backward compat) ────────────────────────────────

    def get_route(self, agent_id: Optional[str] = None, subsystem: Optional[str] = None) -> Tuple[str, str]:
        cfg = self._load()
        if subsystem:
            r = (cfg.get('subsystems') or {}).get(subsystem)
            if r:
                return r['provider'], r['model']
        if agent_id:
            r = (cfg.get('agents') or {}).get(agent_id)
            if r:
                return r['provider'], r['model']
        d = cfg.get('_default')
        if d:
            return d['provider'], d['model']
        return self._env_fallback()

    def set_default(self, provider: str, model: str):
        cfg = self._load()
        cfg['_default'] = {'provider': provider, 'model': model}
        self._save(cfg)

    def set_subsystem_route(self, subsystem: str, provider: str, model: str):
        cfg = self._load()
        cfg.setdefault('subsystems', {})[subsystem] = {'provider': provider, 'model': model}
        self._save(cfg)

    def set_agent_route(self, agent_id: str, provider: str, model: str):
        cfg = self._load()
        cfg.setdefault('agents', {})[agent_id] = {'provider': provider, 'model': model}
        self._save(cfg)

    def _save(self, cfg: dict):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix('.tmp')
        tmp.write_text(json.dumps(cfg, indent=2))
        tmp.replace(self._path)
        self._cache = cfg
        self._mtime = self._path.stat().st_mtime
        try:
            from core.bus import get_bus
            get_bus().publish('system:config_reload', {'kind': 'model-routing'})
        except Exception:
            pass


_singleton: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _singleton
    if _singleton is None:
        _singleton = LLMRouter()
    return _singleton


# ── Module-level convenience functions (mirrors the task spec API) ────────────

def get_model_for_task(task_type: str) -> dict:
    return get_router().get_model_for_task(task_type)

def get_model_for_agent(agent_id: str) -> dict:
    return get_router().get_model_for_agent(agent_id)

def get_all_routing() -> dict:
    return get_router().get_all_routing()

def set_model_for_task(task_type: str, provider: str, model: str) -> None:
    get_router().set_model_for_task(task_type, provider, model)

def set_model_for_agent(agent_id: str, provider: str, model: str) -> None:
    get_router().set_model_for_agent(agent_id, provider, model)


def route_model_qce(goal: str = '', complexity: str = 'medium',
                    provider_health: dict | None = None) -> str:
    """Use AmplitudeRouter.route_model() when QCE is available; fall back to existing routing."""
    try:
        from core.quantum.router import AmplitudeRouter
        router = AmplitudeRouter()
        return router.route_model(complexity=complexity, provider_health=provider_health)
    except Exception:
        pass
    # Fallback: existing LLMRouter logic
    r = get_router()
    task_cfg = r.get_model_for_task(complexity if complexity in _TASK_DEFAULTS else 'general')
    return task_cfg.get('model', 'claude-sonnet-4-6')

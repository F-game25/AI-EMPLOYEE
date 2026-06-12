from __future__ import annotations

import json
import os
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.orchestrator import LLMClient, get_llm_client
from core.tenancy import get_current_tenant, require_current_tenant
from core.database import get_database
from core.state_paths import canonical_state_dir


class AgentValidationError(ValueError):
    """Raised when incoming payload does not satisfy input schema."""


class BaseAgent:
    agent_id = "base"
    required_fields: tuple[str, ...] = ("task",)

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.client = llm_client or get_llm_client()
        state_dir = canonical_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = state_dir / "agent_calls.jsonl"

    def validate(self, payload: dict[str, Any]) -> None:
        missing = [k for k in self.required_fields if payload.get(k) in (None, "")]
        if missing:
            raise AgentValidationError(f"Missing required fields: {', '.join(missing)}")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        try:
            self.validate(payload)
            output = self.execute(payload)
            output.setdefault("tokens_used", 0)
            self._log({
                "agent": self.agent_id,
                "timestamp": started.isoformat(),
                "status": "ok",
                "input": payload,
                "output": output,
            })
            return output
        except Exception as exc:  # noqa: BLE001
            err = {
                "error": str(exc),
                "agent": self.agent_id,
                "tokens_used": 0,
            }
            self._log({
                "agent": self.agent_id,
                "timestamp": started.isoformat(),
                "status": "error",
                "input": payload,
                "output": err,
            })
            return err

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _ask_json(self, *, prompt: str, system: str) -> tuple[dict[str, Any], int]:
        completion = self.client.complete(prompt=prompt, system=system)
        text = completion.get("output", "").strip()
        tokens = int(completion.get("tokens_used", 0))
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed, tokens
        except Exception:
            pass
        return {"raw": text}, tokens

    def _log(self, payload: dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _get_tenant_id(self) -> str:
        """Get current tenant ID from context or raise error."""
        try:
            tenant = get_current_tenant()
            return tenant.tenant_id
        except Exception:
            # Fallback to default tenant for backward compatibility
            return "default"

    def _get_db(self):
        """Get database client instance."""
        return get_database()

    def _save_to_db(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """Save data to PostgreSQL table with automatic tenant_id injection."""
        db = self._get_db()
        tenant_id = self._get_tenant_id()
        return db.insert(table, data, tenant_id=tenant_id)

    @staticmethod
    def _validate_identifier(name: str) -> str:
        """Ensure a SQL identifier (table/column name) contains only safe characters."""
        if not _re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name):
            raise ValueError(f"Invalid SQL identifier: {name!r}")
        return name

    def _query_db(self, table: str, where: str = "", params: tuple = ()) -> list[dict[str, Any]]:
        """Query database with automatic tenant_id filter."""
        self._validate_identifier(table)
        db = self._get_db()
        tenant_id = self._get_tenant_id()
        query = f"SELECT * FROM {table} WHERE {where}" if where else f"SELECT * FROM {table}"
        return db.execute(query, params, tenant_id=tenant_id)

    def _update_db(self, table: str, data: dict[str, Any], where: str, params: tuple = ()) -> int:
        """Update database records with automatic tenant_id filter."""
        db = self._get_db()
        tenant_id = self._get_tenant_id()
        return db.update(table, data, where, params, tenant_id=tenant_id)

    @classmethod
    def wrap(cls, legacy, agent_id: str = 'unknown') -> '_LegacyAgentWrapper':
        """Wrap a non-conforming object as a BaseAgent."""
        entry = next((m for m in ('run', 'execute', 'process', 'handle') if hasattr(legacy, m)), None)
        if entry is None and callable(legacy):
            entry = '__call__'
        return _LegacyAgentWrapper(legacy, agent_id, entry or 'run')


class _LegacyAgentWrapper(BaseAgent):
    def __init__(self, legacy, agent_id: str, entry_point: str):
        self.agent_id = agent_id
        self._legacy = legacy
        self._entry = entry_point

    def execute(self, payload: dict) -> dict:
        fn = getattr(self._legacy, self._entry, None)
        if fn is None and callable(self._legacy):
            fn = self._legacy
        if fn is None:
            return {'status': 'error', 'error': f'No entry point {self._entry}'}
        try:
            result = fn(payload)
            return _normalize_legacy_output(result, self.agent_id)
        except Exception as exc:
            return {'status': 'error', 'agent_id': self.agent_id, 'error': str(exc)}


def _normalize_legacy_output(raw, agent_id: str) -> dict:
    """Coerce any legacy return value into the standard BaseAgent output shape."""
    if isinstance(raw, dict):
        return {'result': raw, 'status': raw.get('status', 'success'), 'agent_id': agent_id}
    return {'result': str(raw) if raw is not None else None, 'status': 'success', 'agent_id': agent_id}

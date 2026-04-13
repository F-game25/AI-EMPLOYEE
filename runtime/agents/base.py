from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.orchestrator import LLMClient, get_llm_client


class AgentValidationError(ValueError):
    """Raised when incoming payload does not satisfy input schema."""


class BaseAgent:
    agent_id = "base"
    required_fields: tuple[str, ...] = ("task",)

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.client = llm_client or get_llm_client()
        state_dir = Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
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

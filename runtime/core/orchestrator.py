from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.bus import get_message_bus

INTENT_CATEGORIES = (
    "lead_gen",
    "content",
    "social",
    "research",
    "email",
    "support",
    "finance",
    "ops",
)
logger = logging.getLogger("task_orchestrator_core")


class LLMClient:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.backend = os.environ.get("LLM_BACKEND", "anthropic").strip().lower()
        self.state_dir = state_dir or Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.state_dir / "llm_calls.jsonl"

    def complete(self, *, prompt: str, system: str = "You are a helpful AI assistant.") -> dict[str, Any]:
        attempts = 3
        delay_s = 1.0
        last_error = ""
        for attempt in range(1, attempts + 1):
            started = time.time()
            try:
                if self.backend == "ollama":
                    response = self._call_ollama(prompt=prompt, system=system)
                elif self.backend == "openrouter":
                    response = self._call_openrouter(prompt=prompt, system=system)
                else:
                    response = self._call_anthropic(prompt=prompt, system=system)
                self._log_call(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "backend": self.backend,
                        "attempt": attempt,
                        "duration_ms": int((time.time() - started) * 1000),
                        "prompt_chars": len(prompt),
                        "tokens_used": response.get("tokens_used", 0),
                        "ok": True,
                    }
                )
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                self._log_call(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "backend": self.backend,
                        "attempt": attempt,
                        "duration_ms": int((time.time() - started) * 1000),
                        "prompt_chars": len(prompt),
                        "ok": False,
                        "error": last_error,
                    }
                )
                if attempt < attempts:
                    time.sleep(delay_s)
                    delay_s *= 2
        raise RuntimeError(f"LLM call failed after retries: {last_error}")

    def _call_anthropic(self, *, prompt: str, system: str) -> dict[str, Any]:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        model = "claude-sonnet-4-20250514"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {body}") from exc
        text = ""
        for block in body.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = body.get("usage", {})
        return {
            "output": text.strip(),
            "tokens_used": int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        }

    def _call_openrouter(self, *, prompt: str, system: str, model: str = "deepseek/deepseek-coder-v2") -> dict[str, Any]:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8787",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc
        text = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        usage = body.get("usage", {})
        return {
            "output": text,
            "tokens_used": int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0)),
            "model": model,
        }

    def _call_ollama(self, *, prompt: str, system: str) -> dict[str, Any]:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        payload = {"model": model, "prompt": prompt, "system": system, "stream": False}
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
        text = body.get("response", "").strip()
        tokens = int(body.get("eval_count", 0)) + int(body.get("prompt_eval_count", 0))
        return {"output": text, "tokens_used": tokens}

    def _log_call(self, event: dict[str, Any]) -> None:
        # Rotate at 50 MB to prevent unbounded disk growth
        _ROTATE_BYTES = 50 * 1024 * 1024
        if self.log_path.exists() and self.log_path.stat().st_size > _ROTATE_BYTES:
            from datetime import datetime
            archive = self.log_path.with_suffix(f".{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl")
            self.log_path.rename(archive)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


class TaskOrchestrator:
    def __init__(self) -> None:
        self.client = get_llm_client()

    def classify_intent(self, task: str) -> str:
        prompt = (
            "Classify the task into exactly one label from this list: "
            f"{', '.join(INTENT_CATEGORIES)}.\n"
            "Return only the label.\n"
            f"Task: {task}"
        )
        try:
            label = self.client.complete(prompt=prompt, system="You are a strict intent classifier.")["output"].strip().lower()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Intent classification failed; defaulting to ops: %s", exc)
            label = "ops"
        if label not in INTENT_CATEGORIES:
            label = "ops"
        return label

    def route_task(self, task: str) -> dict[str, Any]:
        from agents.content_master import ContentMasterAgent
        from agents.data_analyst import DataAnalystAgent
        from agents.email_ninja import EmailNinjaAgent
        from agents.intel_agent import IntelAgent
        from agents.lead_hunter import LeadHunterAgent
        from agents.social_guru import SocialGuruAgent
        from agents.support_bot import SupportBotAgent
        from agents.task_orchestrator import TaskOrchestratorAgent

        intent = self.classify_intent(task)
        agent_map = {
            "lead_gen": LeadHunterAgent,
            "content": ContentMasterAgent,
            "social": SocialGuruAgent,
            "research": IntelAgent,
            "email": EmailNinjaAgent,
            "support": SupportBotAgent,
            "finance": DataAnalystAgent,
            "ops": TaskOrchestratorAgent,
        }
        agent_cls = agent_map[intent]
        agent = agent_cls(self.client)
        started = datetime.now(timezone.utc)
        result = agent.run({"task": task})
        final = {
            "agent": agent.agent_id,
            "task": task,
            "output": result,
            "timestamp": started.isoformat(),
            "tokens_used": int(result.get("tokens_used", 0)),
        }
        try:
            get_message_bus().publish_sync("results", final)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish result on message bus: %s", exc)
        return final

"""ASCEND AI — LLM Router
Routes all chat through Ollama (local, primary) → Anthropic Claude (cloud backup).
Never call providers directly from routers — always go through this service.
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# ── System prompts per context (tight — under 150 words for fast local models) ──

SYSTEM_PROMPTS: dict[str, str] = {
    "main": (
        "You are ASCEND AI, a sharp autonomous business assistant managing 20 specialist agents. "
        "Be concise and direct. When given a task, confirm what you will do and which agents will "
        "handle it. Respond in the user's language."
    ),
    "forge": (
        "You are the Ascend Forge agent. You improve the ASCEND AI system itself. "
        "When given an improvement task, respond with: what you will change, the risk level "
        "(LOW/MEDIUM/HIGH), and what you will test in the sandbox first. "
        "Be technical and precise. Keep responses under 200 words."
    ),
    "money": (
        "You are the Money Mode agent. You specialise in business automation, lead generation, "
        "and revenue optimisation. When given a task, respond with a concrete action plan: "
        "what you will do today, expected outcome, and which tool or channel you will use. "
        "Be results-focused. No fluff."
    ),
    "blacklight": (
        "You are the Blacklight security agent. You monitor all system connections and flag threats. "
        "Respond in structured format: STATUS, FINDINGS, RECOMMENDED ACTION. Be brief and clinical."
    ),
    "hermes": (
        "You are Hermes, the coordination agent. You route tasks to specialist agents and keep the "
        "user informed. When given a task, identify which agent should handle it and confirm the "
        "routing. Also handle notification preferences when asked."
    ),
    "doctor": (
        "You are the Doctor diagnostics agent. Analyse system health data and explain issues in "
        "plain language. When given a metric or log, explain what it means, whether it is a "
        "problem, and what to do about it."
    ),
}

# Max tokens per context (forge = analysis = 1024, others = 512)
_MAX_TOKENS: dict[str, int] = {"forge": 1024}
_MAX_TOKENS_DEFAULT = 512

# Preferred model quality order (best first)
_MODEL_PREFERENCE = ["mistral", "llama3.1", "gemma4", "gemma3", "gemma2", "llama3.2"]

# Anthropic fallback model — fast and cheap
_ANTHROPIC_FALLBACK_MODEL = "claude-haiku-4-5-20251001"

# Ollama stop sequences — prevent model from roleplaying conversation
_STOP_SEQUENCES = ["\n\nUser:", "\n\nHuman:", "###"]


def _read_env_file() -> dict[str, str]:
    """Read ~/.ai-employee/.env into a dict."""
    env_path = os.path.expanduser("~/.ai-employee/.env")
    result: dict[str, str] = {}
    if not os.path.exists(env_path):
        return result
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip().strip('"').strip("'")
    except OSError as exc:
        logger.warning("Could not read ~/.ai-employee/.env: %s", exc)
    return result


class LLMRouter:
    """
    Single service that all chat endpoints use.
    Tries Ollama first; falls back to Anthropic if Ollama is unavailable or times out.
    Re-checks Ollama every 60 seconds so it auto-recovers when started later.
    """

    def __init__(self) -> None:
        self.ollama_available = False
        self.active_provider = "anthropic"
        self.active_model: str | None = None
        # Conversation history keyed by "session_id:context"
        # Each value is a list of {"role": ..., "content": ...} without system prompt
        self._history: dict[str, list[dict]] = {}

    async def startup(self) -> None:
        """Ping Ollama and start background health check loop."""
        await self._check_ollama()
        asyncio.create_task(self._health_loop())
        logger.info(
            "LLM Router ready — provider=%s model=%s ollama=%s",
            self.active_provider,
            self.active_model,
            self.ollama_available,
        )

    async def _check_ollama(self) -> None:
        """Ping Ollama /api/tags with 2s timeout. Update availability + active model."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "http://localhost:11434/api/tags", timeout=2.0
                )
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    self.active_model = self._pick_model(models)
                    self.ollama_available = True
                    self.active_provider = "ollama"
                    return
        except Exception:
            pass
        self.ollama_available = False
        self.active_provider = "anthropic"
        self.active_model = _ANTHROPIC_FALLBACK_MODEL

    async def _health_loop(self) -> None:
        """Re-check Ollama every 10 seconds so it auto-recovers quickly."""
        while True:
            await asyncio.sleep(10)
            await self._check_ollama()

    def _pick_model(self, models: list[dict]) -> str:
        """Choose the best available Ollama model."""
        env = _read_env_file()
        env_model = (
            env.get("OLLAMA_MODEL")
            or os.environ.get("OLLAMA_MODEL", "llama3.2")
        )
        available_names = [m.get("name", "").split(":")[0] for m in models]

        # Honour explicitly configured model first
        if any(env_model in name for name in available_names):
            return env_model

        # Fall through quality preference list
        for preferred in _MODEL_PREFERENCE:
            if any(preferred in name for name in available_names):
                return preferred

        return env_model  # use configured model even if not found

    def get_status(self) -> dict:
        """Return provider, model, and Ollama availability for the status endpoint."""
        return {
            "provider": self.active_provider,
            "model": self.active_model,
            "ollama_available": self.ollama_available,
        }

    # ── Conversation history ─────────────────────────────────────────────────

    def _get_history(self, key: str) -> list[dict]:
        return self._history.get(key, [])

    def _update_history(
        self, key: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Append pair; keep at most 6 pairs (12 messages)."""
        history = self._history.get(key, [])
        history = history + [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
        if len(history) > 12:
            history = history[-12:]
        self._history[key] = history

    # ── Main streaming entry point ───────────────────────────────────────────

    async def stream_chat(
        self,
        session_id: str,
        context: str,
        message: str,
    ) -> AsyncIterator[tuple[str, bool, bool, bool]]:
        """
        Async generator yielding ``(content, done, is_fallback, is_error)`` tuples.

        * ``content``     — text chunk (empty string when ``done=True``)
        * ``done``        — True on the final sentinel tuple
        * ``is_fallback`` — True only on the first chunk when Anthropic is used
        * ``is_error``    — True when both providers are unavailable
        """
        history_key = f"{session_id}:{context}"
        system_prompt = SYSTEM_PROMPTS.get(context, SYSTEM_PROMPTS["main"])
        max_tokens = _MAX_TOKENS.get(context, _MAX_TOKENS_DEFAULT)
        history = self._get_history(history_key)
        messages = history + [{"role": "user", "content": message}]

        if self.ollama_available:
            try:
                full_response = ""
                async for chunk in self._stream_ollama(
                    messages, system_prompt, max_tokens
                ):
                    full_response += chunk
                    yield chunk, False, False, False
                self._update_history(history_key, message, full_response)
                yield "", True, False, False
                return
            except Exception as exc:
                logger.warning(
                    "Ollama stream failed — falling back to Anthropic: %s", exc
                )
                self.ollama_available = False
                self.active_provider = "anthropic"
                # Trigger an immediate re-check so next request can use Ollama if it recovers
                asyncio.create_task(self._check_ollama())

        # ── Anthropic fallback ───────────────────────────────────────────────
        api_key = self._get_anthropic_key()
        if not api_key:
            yield (
                "Both AI providers are unavailable. "
                "Please run `ollama serve` in your terminal to start the local AI.",
                True,
                False,
                True,  # is_error
            )
            return

        try:
            full_response = ""
            is_first_chunk = True
            async for chunk in self._stream_anthropic(
                messages, system_prompt, max_tokens, api_key
            ):
                full_response += chunk
                yield chunk, False, is_first_chunk, False
                is_first_chunk = False
            self._update_history(history_key, message, full_response)
            yield "", True, False, False
        except Exception as exc:
            logger.error("Anthropic fallback also failed: %s", exc)
            yield (
                "Both AI providers are unavailable. "
                "Please run `ollama serve` in your terminal to start the local AI.",
                True,
                False,
                True,  # is_error
            )

    # ── Ollama streaming ─────────────────────────────────────────────────────

    async def _stream_ollama(
        self,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from Ollama /api/chat (multi-turn messages format)."""
        payload = {
            "model": self.active_model or "llama3.2",
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": True,
            "options": {
                "temperature": 0.4,
                "top_p": 0.85,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_ctx": 4096,
                "num_predict": max_tokens,
                "stop": _STOP_SEQUENCES,
            },
        }
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/chat",
                json=payload,
                timeout=15.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    # ── Anthropic streaming ──────────────────────────────────────────────────

    async def _stream_anthropic(
        self,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
        api_key: str,
    ) -> AsyncIterator[str]:
        """Stream from Anthropic Messages API (SSE format)."""
        # Anthropic does not accept "system" role in messages array
        filtered = [m for m in messages if m.get("role") in ("user", "assistant")]

        payload = {
            "model": _ANTHROPIC_FALLBACK_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": filtered,
            "stream": True,
        }
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=30.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "content_block_delta":
                        text = data.get("delta", {}).get("text", "")
                        if text:
                            yield text

    @staticmethod
    def _get_anthropic_key() -> str | None:
        """Read ANTHROPIC_API_KEY from ~/.ai-employee/.env or environment."""
        env = _read_env_file()
        return env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


# ── Singleton ────────────────────────────────────────────────────────────────

_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    """Return the shared LLMRouter instance (created on first call)."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router

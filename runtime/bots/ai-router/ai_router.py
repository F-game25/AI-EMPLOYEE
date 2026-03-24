"""AI Router — Ollama-first with cloud AI fallback.

Routes AI queries to the best available provider in priority order:
  1. Ollama  (local, free, private — preferred)
  2. Anthropic Claude  (cloud, costs tokens — fallback)
  3. OpenAI  (cloud, costs tokens — last resort)

Usage (from any bot that adds this directory to sys.path):

    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "bots" / "ai-router"))
    from ai_router import query_ai

    result = query_ai("Explain quantum computing in simple terms")
    print(result["answer"])    # the response text
    print(result["provider"])  # "ollama" | "anthropic" | "openai" | "error"

Environment variables (loaded from ~/.ai-employee/.env):
    OLLAMA_HOST           — Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL          — model name (default: llama3.2)
    OLLAMA_TIMEOUT        — request timeout in seconds (default: 60)
    ANTHROPIC_API_KEY     — Anthropic key (optional cloud fallback)
    CLAUDE_MODEL          — Claude model name (default: claude-opus-4-5)
    OPENAI_API_KEY        — OpenAI key (optional last-resort fallback)
    OPENAI_MODEL          — OpenAI model name (default: gpt-4o-mini)
    CLOUD_AI_TIMEOUT      — cloud request timeout in seconds (default: 30)
"""
import logging
import os
from typing import Optional

logger = logging.getLogger("ai_router")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

CLOUD_AI_TIMEOUT = int(os.environ.get("CLOUD_AI_TIMEOUT", "30"))


def _build_messages(prompt: str, system_prompt: str, history: list) -> list:
    """Build a messages list from prompt, optional system prompt, and history."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages


def _try_ollama(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from the local Ollama instance."""
    try:
        import requests  # lightweight stdlib-like dep already used by ollama-agent

        messages = _build_messages(prompt, system_prompt, history)
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "").strip()
        if answer:
            logger.debug("ai_router: used Ollama (%s)", OLLAMA_MODEL)
            return {
                "answer": answer,
                "provider": "ollama",
                "model": OLLAMA_MODEL,
                "error": None,
            }
    except Exception as exc:
        logger.debug("ai_router: Ollama unavailable — %s", exc)
    return None


def _try_anthropic(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from Anthropic Claude (cloud fallback)."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        messages = list(history) if history else []
        messages.append({"role": "user", "content": prompt})
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt or "You are a helpful AI assistant.",
            messages=messages,
        )
        answer = response.content[0].text.strip()
        logger.debug("ai_router: used Anthropic Claude (%s)", CLAUDE_MODEL)
        return {
            "answer": answer,
            "provider": "anthropic",
            "model": CLAUDE_MODEL,
            "error": None,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: Anthropic unavailable — %s", exc)
    return None


def _try_openai(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from OpenAI (last-resort cloud fallback)."""
    if not OPENAI_API_KEY:
        return None
    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        messages = _build_messages(prompt, system_prompt, history)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=4096,
            timeout=CLOUD_AI_TIMEOUT,
        )
        answer = response.choices[0].message.content.strip()
        logger.debug("ai_router: used OpenAI (%s)", OPENAI_MODEL)
        return {
            "answer": answer,
            "provider": "openai",
            "model": OPENAI_MODEL,
            "error": None,
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: OpenAI unavailable — %s", exc)
    return None


def query_ai(
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query through providers in priority order.

    Priority:
        1. Ollama (local, free) — always tried first
        2. Anthropic Claude (cloud) — only if Ollama unavailable and key set
        3. OpenAI (cloud) — only if both above fail and key set

    Args:
        prompt: The user message or question.
        system_prompt: Optional system/role instructions for the AI.
        history: Optional list of previous messages in OpenAI chat format,
                 e.g. [{"role": "user", "content": "..."}, {"role": "assistant", ...}]

    Returns:
        dict with keys:
            answer   (str)  — AI response text, empty string on failure
            provider (str)  — "ollama" | "anthropic" | "openai" | "error"
            model    (str)  — model identifier used
            error    (str|None) — error description if all providers failed
            usage    (dict|None) — token usage for cloud providers
    """
    history = history or []

    # 1. Try Ollama first (local, free, privacy-preserving)
    result = _try_ollama(prompt, system_prompt, history)
    if result:
        return result

    # 2. Try Anthropic Claude (cloud, costs tokens — fallback)
    result = _try_anthropic(prompt, system_prompt, history)
    if result:
        return result

    # 3. Try OpenAI (cloud, costs tokens — last resort)
    result = _try_openai(prompt, system_prompt, history)
    if result:
        return result

    # All providers failed
    return {
        "answer": "",
        "provider": "error",
        "model": "",
        "error": (
            "No AI provider available. "
            "Start Ollama (`ollama serve`) or set ANTHROPIC_API_KEY / OPENAI_API_KEY "
            "in ~/.ai-employee/.env and restart."
        ),
        "usage": None,
    }


def is_ollama_available() -> bool:
    """Quick check whether the local Ollama instance is reachable."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

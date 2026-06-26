"""
OpenAI Client — internal leaf adapter for a single provider.

NOT called directly: it is invoked only through LLMProviderRouter, which is the
audited surface that applies the egress guard (no secrets/PII leave the box),
retries, and writes redacted call metadata to llm_calls.jsonl. Used alongside
Anthropic / OpenRouter / Ollama / NVIDIA, independently and concurrently.
OpenAI-compatible chat/completions API. Key from Settings.
"""

import json
from typing import AsyncIterator, Dict, List

import aiohttp

_OPENAI_BASE = "https://api.openai.com/v1"


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._validate_key()

    def _validate_key(self):
        # OpenAI keys are 'sk-...' (and 'sk-proj-...'); reject obviously wrong shapes.
        if not isinstance(self.api_key, str) or not self.api_key.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format (must start with sk-)")

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_OPENAI_BASE}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    raise Exception(f"OpenAI error {resp.status}: {await resp.text()}")
        except Exception as e:
            raise Exception(f"OpenAI generation failed: {str(e)}")

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_OPENAI_BASE}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages, "temperature": temperature,
                          "max_tokens": max_tokens, "stream": True},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"OpenAI error {resp.status}: {await resp.text()}")
                    async for line in resp.content:
                        if not line:
                            continue
                        text = line.decode().strip()
                        if text.startswith("data: ") and text != "data: [DONE]":
                            try:
                                delta = json.loads(text[6:])["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass
        except Exception as e:
            raise Exception(f"OpenAI streaming failed: {str(e)}")

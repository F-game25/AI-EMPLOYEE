"""
NVIDIA Client — internal leaf adapter (hosted NVIDIA AI / NIM / build.nvidia.com).

NOT called directly: invoked only through LLMProviderRouter, the audited surface
that applies the egress guard, retries, and redacted llm_calls.jsonl logging.
Gives "external extra power" for deploying agents on NVIDIA-cloud GPUs (Llama,
Nemotron, etc.). OpenAI-compatible chat/completions API at integrate.api.nvidia.com.
Used alongside Anthropic / OpenAI / OpenRouter / Ollama, independently and
concurrently. Key (NVIDIA_API_KEY, 'nvapi-…') from Settings.
"""

import json
from typing import AsyncIterator, Dict, List

import aiohttp

_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"


class NvidiaClient:
    def __init__(self, api_key: str, model: str = "meta/llama-3.1-70b-instruct"):
        self.api_key = api_key
        self.model = model
        self._validate_key()

    def _validate_key(self):
        if not isinstance(self.api_key, str) or not self.api_key.startswith("nvapi-"):
            raise ValueError("Invalid NVIDIA API key format (must start with nvapi-)")

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_NVIDIA_BASE}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    raise Exception(f"NVIDIA error {resp.status}: {await resp.text()}")
        except Exception as e:
            raise Exception(f"NVIDIA generation failed: {str(e)}")

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_NVIDIA_BASE}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages, "temperature": temperature,
                          "max_tokens": max_tokens, "stream": True},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"NVIDIA error {resp.status}: {await resp.text()}")
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
            raise Exception(f"NVIDIA streaming failed: {str(e)}")

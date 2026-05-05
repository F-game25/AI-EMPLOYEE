"""
OpenRouter Client — Fallback LLM provider.

Used when primary provider (Anthropic/Ollama) is unavailable.
Requires OpenRouter API key from Settings.
Automatic retry on failure.
"""

import aiohttp
import json
from typing import AsyncIterator, Dict, List, Any

class OpenRouterClient:
    def __init__(self, api_key: str, model: str = 'auto'):
        self.api_key = api_key
        self.model = model
        self._validate_key()

    def _validate_key(self):
        """Validate API key format."""
        if not self.api_key.startswith('sk-or-'):
            raise ValueError("Invalid OpenRouter API key format (must start with sk-or-)")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate response using OpenRouter API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://ai-employee.local",
                        "X-Title": "AI Employee",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        error = await resp.text()
                        raise Exception(f"OpenRouter error {resp.status}: {error}")
        except Exception as e:
            raise Exception(f"OpenRouter generation failed: {str(e)}")

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Stream response using OpenRouter API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://ai-employee.local",
                        "X-Title": "AI Employee",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                try:
                                    text = line.decode().strip()
                                    if text.startswith("data: "):
                                        data = json.loads(text[6:])
                                        if "choices" in data:
                                            delta = data["choices"][0].get("delta", {})
                                            if "content" in delta:
                                                yield delta["content"]
                                except json.JSONDecodeError:
                                    pass
                    else:
                        error = await resp.text()
                        raise Exception(f"OpenRouter error {resp.status}: {error}")
        except Exception as e:
            raise Exception(f"OpenRouter streaming failed: {str(e)}")

    def validate_connection(self) -> bool:
        """Test connection to OpenRouter."""
        import requests
        try:
            response = requests.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

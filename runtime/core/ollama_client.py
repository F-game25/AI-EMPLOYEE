"""
Ollama Client — Local LLM inference.

Connects to local Ollama server.
No API key required (fully local).
Supports llama2, mistral, neural-chat models.
Gracefully falls back if Ollama unavailable.
"""

import aiohttp
import json
import requests
from typing import AsyncIterator, Dict, List, Any

class OllamaClient:
    def __init__(self, endpoint: str = 'http://localhost:11434', model: str = 'llama2'):
        self.endpoint = endpoint
        self.model = model
        self.available = False
        self._check_availability()

    def _check_availability(self):
        """Check if Ollama is running at the endpoint."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=2)
            self.available = response.status_code == 200
        except Exception:
            self.available = False
            print(f"Ollama unavailable at {self.endpoint} — will fallback to primary provider")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate response using local Ollama."""
        if not self.available:
            raise Exception(f"Ollama not available at {self.endpoint}")

        prompt = self._messages_to_prompt(messages)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.endpoint}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "stream": False,
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
                    else:
                        raise Exception(f"Ollama error: {resp.status}")
            except Exception as e:
                raise Exception(f"Ollama generation failed: {str(e)}")

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Stream response using local Ollama."""
        if not self.available:
            raise Exception(f"Ollama not available at {self.endpoint}")

        prompt = self._messages_to_prompt(messages)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.endpoint}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "stream": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                data = json.loads(line.decode())
                                if "response" in data:
                                    yield data["response"]
                    else:
                        raise Exception(f"Ollama error: {resp.status}")
            except Exception as e:
                raise Exception(f"Ollama streaming failed: {str(e)}")

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert message list to single prompt string."""
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        return "\n".join(prompt_parts) + "\nAssistant:"

    def get_supported_models(self) -> List[str]:
        """Return list of Ollama models."""
        return ['llama2', 'mistral', 'neural-chat', 'openchat', 'zephyr']

    def validate_connection(self) -> bool:
        """Test connection to Ollama."""
        return self.available

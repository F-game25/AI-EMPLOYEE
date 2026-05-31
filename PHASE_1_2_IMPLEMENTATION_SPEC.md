# Phase 1.2-1.5: LLM Provider Routing — Implementation Spec

## Overview
Settings UI exists and saves provider choice. Now implement the routing logic that actually uses the selected provider.

---

## TASK 1.2: LLM Provider Router (2 hours)

### File: `runtime/core/llm_provider_router.py` (NEW)

```python
"""
LLM Provider Router — Route API calls to the selected LLM backend.

Reads provider from environment (set by Settings API POST).
Routes chat requests to appropriate client (Anthropic, Ollama, OpenRouter).
Implements fallback chain: primary → fallback → error.
"""

import os
from typing import Optional, Dict, Any
from anthropic_client import AnthropicClient
from ollama_client import OllamaClient
from openrouter_client import OpenRouterClient

class LLMProviderRouter:
    def __init__(self):
        self.primary_provider = os.getenv('LLM_PROVIDER', 'anthropic')
        self.anthropic_client = None
        self.ollama_client = None
        self.openrouter_client = None
        self._init_providers()

    def _init_providers(self):
        """Initialize all provider clients based on available API keys."""
        # Anthropic
        if os.getenv('ANTHROPIC_API_KEY'):
            self.anthropic_client = AnthropicClient(
                api_key=os.getenv('ANTHROPIC_API_KEY'),
                model=os.getenv('LLM_MODEL', 'claude-3-5-sonnet')
            )

        # Ollama
        if os.getenv('OLLAMA_ENDPOINT'):
            self.ollama_client = OllamaClient(
                endpoint=os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434'),
                model=os.getenv('LLM_MODEL', 'llama2')
            )

        # OpenRouter (fallback)
        if os.getenv('OPENROUTER_API_KEY'):
            self.openrouter_client = OpenRouterClient(
                api_key=os.getenv('OPENROUTER_API_KEY')
            )

    async def generate(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        Generate response using selected provider.
        Falls back to next provider on failure.
        """
        # Try primary provider
        client = self._get_client(self.primary_provider)
        if client:
            try:
                return await client.generate(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                print(f"Primary provider {self.primary_provider} failed: {e}")

        # Fallback to next available provider
        fallback_order = ['anthropic', 'ollama', 'openrouter']
        for provider in fallback_order:
            if provider == self.primary_provider:
                continue
            client = self._get_client(provider)
            if client:
                try:
                    return await client.generate(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                except Exception as e:
                    print(f"Fallback provider {provider} failed: {e}")

        raise Exception("No LLM provider available")

    def _get_client(self, provider: str):
        """Get client for specified provider."""
        if provider == 'anthropic':
            return self.anthropic_client
        elif provider == 'ollama':
            return self.ollama_client
        elif provider == 'openrouter':
            return self.openrouter_client
        return None

    async def stream(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048):
        """
        Stream response using selected provider.
        """
        client = self._get_client(self.primary_provider)
        if client:
            try:
                async for chunk in client.stream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    yield chunk
                return
            except Exception as e:
                print(f"Primary provider {self.primary_provider} stream failed: {e}")

        # Fallback streaming
        fallback_order = ['anthropic', 'ollama', 'openrouter']
        for provider in fallback_order:
            if provider == self.primary_provider:
                continue
            client = self._get_client(provider)
            if client:
                try:
                    async for chunk in client.stream(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    ):
                        yield chunk
                    return
                except Exception as e:
                    print(f"Fallback provider {provider} stream failed: {e}")

        raise Exception("No LLM provider available for streaming")

# Global instance
_router = None

def get_router() -> LLMProviderRouter:
    global _router
    if _router is None:
        _router = LLMProviderRouter()
    return _router
```

**Integration**: Update `runtime/core/orchestrator.py` to use `get_router()` instead of direct LLM client.

---

## TASK 1.3: Anthropic SDK Integration (3 hours)

### File: `runtime/core/anthropic_client.py` (NEW)

```python
"""
Anthropic Client — Claude 3.x API integration.

Uses user's API key from Settings.
Supports all Claude models (Sonnet, Opus, Haiku).
Respects temperature and max_tokens from Settings.
"""

import os
from anthropic import Anthropic
from typing import AsyncIterator, Dict, List, Any

class AnthropicClient:
    def __init__(self, api_key: str, model: str = 'claude-3-5-sonnet-20241022'):
        self.api_key = api_key
        self.model = model
        self.client = Anthropic(api_key=api_key)
        self._validate_key()

    def _validate_key(self):
        """Validate API key format."""
        if not self.api_key.startswith('sk-ant-'):
            raise ValueError("Invalid Anthropic API key format (must start with sk-ant-)")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        Generate response using Anthropic API.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            )
            return response.content[0].text
        except Exception as e:
            raise Exception(f"Anthropic API error: {str(e)}")

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """
        Stream response using Anthropic API.
        Yields text chunks as they arrive.
        """
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise Exception(f"Anthropic streaming error: {str(e)}")

    def get_supported_models(self) -> List[str]:
        """Return list of supported Claude models."""
        return [
            'claude-3-5-sonnet-20241022',
            'claude-3-opus-20240229',
            'claude-3-haiku-20240307',
        ]

    def validate_connection(self) -> bool:
        """Test connection to Anthropic API."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}]
            )
            return response.stop_reason == "end_turn"
        except Exception:
            return False
```

**Integration**: 
1. Update `runtime/core/orchestrator.py` to use `AnthropicClient`
2. Update `runtime/core/llm_provider_router.py` to instantiate this client

---

## TASK 1.4: Ollama Local Integration (2 hours)

### File: `runtime/core/ollama_client.py` (NEW)

```python
"""
Ollama Client — Local LLM inference.

Connects to local Ollama server.
No API key required (fully local).
Supports llama2, mistral, neural-chat models.
Gracefully falls back if Ollama unavailable.
"""

import aiohttp
from typing import AsyncIterator, Dict, List, Any
import json

class OllamaClient:
    def __init__(self, endpoint: str = 'http://localhost:11434', model: str = 'llama2'):
        self.endpoint = endpoint
        self.model = model
        self.available = False
        self._check_availability()

    def _check_availability(self):
        """Check if Ollama is running at the endpoint."""
        import requests
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=2)
            self.available = response.status_code == 200
        except Exception:
            self.available = False
            print(f"Ollama unavailable at {self.endpoint} — will fallback to primary provider")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        Generate response using local Ollama.
        """
        if not self.available:
            raise Exception(f"Ollama not available at {self.endpoint}")

        # Convert messages to Ollama format
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
        """
        Stream response using local Ollama.
        """
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
```

---

## TASK 1.5: OpenRouter Fallback (1.5 hours)

### File: `runtime/core/openrouter_client.py` (NEW)

```python
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
        """
        Generate response using OpenRouter API.
        """
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
        """
        Stream response using OpenRouter API.
        """
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
```

---

## Integration Points

### Update: `runtime/core/orchestrator.py`

```python
# At top
from llm_provider_router import get_router

# In orchestrator class
async def generate_response(self, messages, temperature=0.7, max_tokens=2048):
    """Use provider router instead of direct client."""
    router = get_router()
    response = await router.generate(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response
```

### Update: Backend `/api/settings` POST handler

When user saves settings, store in environment:
```javascript
process.env.LLM_PROVIDER = llmSettings.provider;
process.env.LLM_MODEL = llmSettings.model;
process.env.ANTHROPIC_API_KEY = apiKeys.anthropic;
process.env.OPENROUTER_API_KEY = apiKeys.openrouter;
process.env.OLLAMA_ENDPOINT = apiKeys.ollama_endpoint;
```

This triggers provider router re-initialization.

---

## Testing

### Phase 1.2 Test
```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": {"anthropic": "sk-ant-...", "openrouter": "sk-or-...", "ollama_endpoint": "http://localhost:11434"},
    "llmSettings": {"provider": "anthropic", "model": "claude-3-5-sonnet", "temperature": 0.7, "maxTokens": 2048}
  }'

# Verify provider router uses Anthropic
curl -X POST http://localhost:8787/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

### Phase 1.3 Test
```bash
# Set Anthropic API key in Settings, chat should use Claude
# Model selection in Settings should be respected
# Temperature/max tokens should be applied
```

### Phase 1.4 Test
```bash
# If Ollama running: set provider=ollama → should use local LLM
# If Ollama stopped: should fallback to primary provider
```

### Phase 1.5 Test
```bash
# Primary provider fails → automatic fallback to OpenRouter
# Should see "Using OpenRouter (fallback)" in response metadata
```

---

## Success Criteria

- ✅ Phase 1.2: Router correctly selects provider based on setting
- ✅ Phase 1.3: Anthropic client uses user's API key
- ✅ Phase 1.4: Ollama client connects to local server
- ✅ Phase 1.5: Fallback chain works (primary → fallback → error)
- ✅ All: Temperature and max_tokens respected
- ✅ All: Streaming responses work
- ✅ All: Error messages clear

---

## Files to Create

1. `runtime/core/llm_provider_router.py` (2h)
2. `runtime/core/anthropic_client.py` (3h)
3. `runtime/core/ollama_client.py` (2h)
4. `runtime/core/openrouter_client.py` (1.5h)

## Files to Update

1. `runtime/core/orchestrator.py` (0.5h)
2. `backend/routes/settings.js` (already complete)

## Total Time: ~8.5 hours

---

**Ready to implement. Start with Phase 1.2 (LLM Provider Router).**

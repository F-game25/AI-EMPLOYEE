"""
LLM Provider Router — Route API calls to the selected LLM backend.

Reads provider from environment (set by Settings API POST).
Routes chat requests to appropriate client (Anthropic, Ollama, OpenRouter).
Implements fallback chain: primary → fallback → error.
"""

import os
import asyncio
from typing import Optional, Dict, Any, AsyncIterator

class LLMProviderRouter:
    def __init__(self):
        self.primary_provider = os.getenv('LLM_PROVIDER', 'anthropic')
        self.anthropic_client = None
        self.ollama_client = None
        self.openrouter_client = None
        self._init_providers()

    def _init_providers(self):
        """Initialize all provider clients based on available API keys."""
        try:
            from anthropic_client import AnthropicClient
            if os.getenv('ANTHROPIC_API_KEY'):
                self.anthropic_client = AnthropicClient(
                    api_key=os.getenv('ANTHROPIC_API_KEY'),
                    model=os.getenv('LLM_MODEL', 'claude-3-5-sonnet-20241022')
                )
        except Exception as e:
            print(f"Failed to init Anthropic client: {e}")

        try:
            from ollama_client import OllamaClient
            if os.getenv('OLLAMA_ENDPOINT'):
                self.ollama_client = OllamaClient(
                    endpoint=os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434'),
                    model=os.getenv('OLLAMA_MODEL', 'llama2')
                )
        except Exception as e:
            print(f"Failed to init Ollama client: {e}")

        try:
            from openrouter_client import OpenRouterClient
            if os.getenv('OPENROUTER_API_KEY'):
                self.openrouter_client = OpenRouterClient(
                    api_key=os.getenv('OPENROUTER_API_KEY'),
                    model=os.getenv('OPENROUTER_MODEL', 'auto')
                )
        except Exception as e:
            print(f"Failed to init OpenRouter client: {e}")

    async def generate(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate response using selected provider. Falls back on failure."""
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

    async def stream(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Stream response using selected provider."""
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

_router = None

def get_router() -> LLMProviderRouter:
    global _router
    if _router is None:
        _router = LLMProviderRouter()
    return _router

def reset_router():
    """Reset the global router instance (for testing/settings changes)."""
    global _router
    _router = None

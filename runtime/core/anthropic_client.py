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
        """Generate response using Anthropic API."""
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
        """Stream response using Anthropic API. Yields text chunks as they arrive."""
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

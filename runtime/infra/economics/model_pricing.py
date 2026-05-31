"""Model pricing catalog — authoritative cost table for all LLM providers.

Prices in USD per 1M tokens (input / output).
Updated: 2025-Q2. Override via MODEL_PRICING_JSON env var for custom rates.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelPrice:
    provider: str
    model_id: str
    input_per_1m: float     # USD per 1M input tokens
    output_per_1m: float    # USD per 1M output tokens
    context_window: int     # max context tokens
    latency_tier: str       # "fast" | "balanced" | "quality"
    capabilities: list[str]  # ["text","code","vision","tools"]

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_1m + output_tokens * self.output_per_1m) / 1_000_000


# ── Pricing catalog ───────────────────────────────────────────────────────────

_CATALOG_DEFAULT: list[dict] = [
    # Anthropic
    {"provider": "anthropic", "model_id": "claude-opus-4-7",
     "input_per_1m": 15.0, "output_per_1m": 75.0, "context_window": 200000,
     "latency_tier": "quality", "capabilities": ["text", "code", "vision", "tools"]},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-6",
     "input_per_1m": 3.0,  "output_per_1m": 15.0, "context_window": 200000,
     "latency_tier": "balanced", "capabilities": ["text", "code", "vision", "tools"]},
    {"provider": "anthropic", "model_id": "claude-haiku-4-5",
     "input_per_1m": 0.80, "output_per_1m": 4.0,  "context_window": 200000,
     "latency_tier": "fast", "capabilities": ["text", "code", "tools"]},
    # OpenAI
    {"provider": "openai", "model_id": "gpt-4o",
     "input_per_1m": 2.5, "output_per_1m": 10.0, "context_window": 128000,
     "latency_tier": "balanced", "capabilities": ["text", "code", "vision", "tools"]},
    {"provider": "openai", "model_id": "gpt-4o-mini",
     "input_per_1m": 0.15, "output_per_1m": 0.60, "context_window": 128000,
     "latency_tier": "fast", "capabilities": ["text", "code", "tools"]},
    {"provider": "openai", "model_id": "o3",
     "input_per_1m": 10.0, "output_per_1m": 40.0, "context_window": 200000,
     "latency_tier": "quality", "capabilities": ["text", "code", "reasoning"]},
    {"provider": "openai", "model_id": "o4-mini",
     "input_per_1m": 1.1, "output_per_1m": 4.4, "context_window": 200000,
     "latency_tier": "balanced", "capabilities": ["text", "code", "reasoning"]},
    # Google
    {"provider": "google", "model_id": "gemini-2.0-flash",
     "input_per_1m": 0.10, "output_per_1m": 0.40, "context_window": 1000000,
     "latency_tier": "fast", "capabilities": ["text", "code", "vision", "tools"]},
    {"provider": "google", "model_id": "gemini-2.5-pro",
     "input_per_1m": 1.25, "output_per_1m": 10.0, "context_window": 2000000,
     "latency_tier": "quality", "capabilities": ["text", "code", "vision", "tools", "reasoning"]},
    # Local / Ollama
    {"provider": "ollama", "model_id": "llama3.2",
     "input_per_1m": 0.0, "output_per_1m": 0.0, "context_window": 128000,
     "latency_tier": "balanced", "capabilities": ["text", "code"]},
    {"provider": "ollama", "model_id": "qwen2.5-coder",
     "input_per_1m": 0.0, "output_per_1m": 0.0, "context_window": 32000,
     "latency_tier": "fast", "capabilities": ["code"]},
]


class ModelPricingCatalog:
    def __init__(self) -> None:
        catalog_json = os.environ.get("MODEL_PRICING_JSON")
        if catalog_json:
            try:
                overrides = json.loads(catalog_json)
                self._catalog = {m["model_id"]: ModelPrice(**m) for m in overrides}
                return
            except Exception:
                pass
        self._catalog = {m["model_id"]: ModelPrice(**m) for m in _CATALOG_DEFAULT}

    def get(self, model_id: str) -> ModelPrice | None:
        return self._catalog.get(model_id)

    def all_models(self) -> list[ModelPrice]:
        return list(self._catalog.values())

    def by_latency(self, tier: str) -> list[ModelPrice]:
        return [m for m in self._catalog.values() if m.latency_tier == tier]

    def cheapest_with_caps(self, required_capabilities: list[str], max_cost_per_1m: float = 999) -> ModelPrice | None:
        cap_set = set(required_capabilities)
        candidates = [
            m for m in self._catalog.values()
            if cap_set.issubset(set(m.capabilities))
            and m.input_per_1m <= max_cost_per_1m
        ]
        return min(candidates, key=lambda m: m.input_per_1m, default=None)

    def estimate(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        m = self.get(model_id)
        return m.cost(input_tokens, output_tokens) if m else 0.0


_catalog: ModelPricingCatalog | None = None

def get_pricing_catalog() -> ModelPricingCatalog:
    global _catalog
    if _catalog is None:
        _catalog = ModelPricingCatalog()
    return _catalog

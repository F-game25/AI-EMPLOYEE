"""AI Employee — Internal Engine

This package is the embedded intelligence engine for AI Employee.
It replaces all direct use of external gateway binaries.

Public surface (import from engine.api):
  process_input(raw_input)              — normalise & extract intent
  generate(prompt, context, ...)        — LLM text generation
  embed(text)                           — text embedding
  memory_store(key, value, ...)         — persist a memory entry
  memory_retrieve(key, ...)             — retrieve a memory entry
"""

from .api import (
    process_input,
    generate,
    embed,
    memory_store,
    memory_retrieve,
)

__all__ = [
    "process_input",
    "generate",
    "embed",
    "memory_store",
    "memory_retrieve",
]

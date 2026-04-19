"""Engine — Inference sub-package.

Provides LLM generation and embedding via Ollama (default) or any
AI-router backend that is installed alongside AI Employee.

Public interface
----------------
  generate(prompt, system, context, model, timeout)  → str
  embed(text, model, timeout)                         → list[float]
"""

from .llm import generate, embed

__all__ = ["generate", "embed"]

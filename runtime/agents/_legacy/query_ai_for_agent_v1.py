"""query_ai_for_agent — v1 signature (archived).

This is the original ``query_ai_for_agent`` implementation from
``runtime/agents/ai-router/ai_router.py``.  It accepted keyword args
``agent_id`` and ``category`` to route via the ``_route_for_agent()``
helper.  It was silently shadowed by the v2 variant (positional
``agent_type`` first argument) which was defined immediately after it
in the same module, so only v2 was ever callable at runtime.

Retained here for one release cycle as a reference/fallback; delete
once v2 is confirmed stable in production.

DO NOT import this file from production code.
"""
# ── copied verbatim from ai_router.py (commit b4e6ae9) ───────────────────────
# Requires: _route_for_agent, _try_openai, _try_anthropic, _try_ollama,
#           query_ai, os, Optional (from typing), logger
from __future__ import annotations

import os
from typing import Optional


def query_ai_for_agent_v1(
    prompt: str,
    agent_id: Optional[str] = None,
    category: Optional[str] = None,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query to the optimal provider for a specific agent type.

    Per-agent model routing:
      - sales agents (lead-hunter, email-ninja, web-sales, email-marketer)
          → OpenAI GPT-4o (persuasive, human-like copy)
      - analytics/research agents (data-analyst, intel-agent, ecom-dashboard)
          → Anthropic Claude (superior long-context analysis)
      - all other agents
          → Ollama (local, free, private)

    Falls back to the standard query_ai() priority chain if the preferred
    provider is unavailable.

    Args:
        prompt:        The user message or question.
        agent_id:      The agent identifier (e.g. "lead-hunter", "data-analyst").
        category:      Agent category if agent_id not known ("sales", "analytics", …).
        system_prompt: Optional system/role instructions for the AI.
        history:       Optional prior conversation history.

    Returns:
        Same dict structure as query_ai().
    """
    raise NotImplementedError(
        "This is an archived legacy stub — import query_ai_for_agent from "
        "runtime/agents/ai-router/ai_router.py instead."
    )

"""Product Researcher agent — thin wrapper around core.product_researcher.

Delegates all logic to research_products() and exposes it via the BaseAgent
execute() contract so the orchestrator can call it like any other agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

_runtime = Path(__file__).resolve().parents[3] / "runtime"
if str(_runtime) not in sys.path:
    sys.path.insert(0, str(_runtime))

from agents.base import BaseAgent


class ProductResearcherAgent(BaseAgent):
    agent_id = "product-researcher"
    required_fields = ("niche",)

    def execute(self, payload: dict) -> dict:
        from core.product_researcher import research_products
        niche     = payload["niche"]
        markt     = payload.get("markt", "nl")
        min_marge = int(payload.get("min_marge", 30))
        return research_products(niche, markt, min_marge)

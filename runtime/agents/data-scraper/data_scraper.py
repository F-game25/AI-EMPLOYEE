"""Data Scraper Agent — public web data extraction and enrichment.

Scrapes public data via web search (DuckDuckGo/Tavily): LinkedIn-style profiles,
G2/Capterra reviews, news articles, product listings, pricing pages.
Returns structured, enriched datasets.

Commands (via chat):
  scrape profiles  <company/role>   — find professional profiles
  scrape reviews   <product>        — aggregate review data from G2/Trustpilot
  scrape news      <topic>          — latest news articles on topic
  scrape products  <category>       — product listings with pricing
  scrape pricing   <competitors>    — competitor pricing intelligence
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import search_web as _search_web  # type: ignore
    _SEARCH_AVAILABLE = True
except ImportError:
    _SEARCH_AVAILABLE = False

SYSTEM = """You are a Data Extraction Specialist. Analyze search results and extract structured data.

Output JSON with this structure:
{
  "query": "...",
  "data_type": "profiles|reviews|news|products|pricing",
  "total_results": 0,
  "records": [
    {
      "title": "...",
      "url": "...",
      "snippet": "...",
      "extracted_data": {},
      "relevance_score": 0
    }
  ],
  "summary": "Key insights from the scraped data",
  "patterns": ["pattern 1 observed", "pattern 2"],
  "data_quality": "high|medium|low",
  "limitations": "What this scrape couldn't capture"
}"""


class DataScraperAgent(BaseAgent):
    agent_id = "data-scraper"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        query = payload.get("query") or payload.get("task", "")
        data_type = payload.get("type", "general")
        max_results = int(payload.get("max_results", 10))

        search_results = []
        if _SEARCH_AVAILABLE:
            try:
                results = _search_web(query, max_results=max_results)
                if isinstance(results, list):
                    search_results = results
                elif isinstance(results, dict):
                    search_results = results.get("results", [])
            except Exception:
                pass

        if not search_results:
            search_results = [{"note": "Web search unavailable — results based on AI knowledge only"}]

        prompt = (
            f"Extract and structure data from these search results.\n"
            f"Query: {query}\n"
            f"Data type requested: {data_type}\n"
            f"Search results: {json.dumps(search_results[:15], indent=2)}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

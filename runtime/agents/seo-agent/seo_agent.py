"""SEO Agent — full on-page SEO audits and optimization.

Audits title/meta/headings/internal links, clusters keywords by intent,
identifies content gaps, suggests schema markup, and produces page-by-page
optimization plans.

Commands (via chat):
  seo audit    <url/page>    — full on-page SEO audit
  seo keywords <topic>       — keyword cluster by search intent
  seo gaps     <domain>      — content gap analysis vs competitors
  seo meta     <page>        — optimized title and meta description
  seo schema   <page_type>   — schema markup JSON-LD suggestion
  seo report   <domain>      — full SEO health report
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Senior SEO Strategist with 10+ years of technical and content SEO experience. You combine data-driven analysis with actionable recommendations.

Output JSON with this structure:
{
  "seo_score": 0,
  "audit_summary": "One-sentence headline of SEO health",
  "title_tag": {"current": "...", "optimized": "...", "length": 0, "issues": []},
  "meta_description": {"current": "...", "optimized": "...", "length": 0, "issues": []},
  "headings": {"h1_count": 0, "h1_text": "...", "structure_issues": [], "recommendations": []},
  "keyword_analysis": {
    "primary_keyword": "...",
    "secondary_keywords": [],
    "keyword_clusters": [{"intent": "informational|commercial|transactional|navigational", "keywords": []}]
  },
  "content_gaps": ["missing topic 1", "missing topic 2"],
  "internal_linking": {"issues": [], "suggestions": []},
  "technical_issues": [{"issue": "...", "impact": "high|medium|low", "fix": "..."}],
  "schema_markup": {"type": "...", "json_ld": {}},
  "quick_wins": [{"action": "...", "estimated_impact": "...", "effort": "low|medium|high"}],
  "priority_actions": ["#1 action", "#2 action", "#3 action"]
}"""


class SEOAgent(BaseAgent):
    agent_id = "seo-agent"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        url = payload.get("url") or payload.get("page", "")
        topic = payload.get("topic") or payload.get("task", "")
        action = payload.get("action", "audit")
        competitors = payload.get("competitors", [])
        current_title = payload.get("current_title", "")
        current_meta = payload.get("current_meta", "")
        content_snippet = payload.get("content", "")

        prompt = (
            f"SEO task: {action}\n"
            f"URL/Page: {url}\n"
            f"Topic/Keyword: {topic}\n"
            f"Current title: {current_title}\n"
            f"Current meta: {current_meta}\n"
            f"Content snippet: {content_snippet[:500] if content_snippet else 'not provided'}\n"
            f"Competitors: {', '.join(competitors) if competitors else 'not specified'}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

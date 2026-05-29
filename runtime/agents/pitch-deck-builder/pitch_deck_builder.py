"""Pitch Deck Builder Agent — investor-grade pitch decks.

Builds complete pitch deck outlines with slide-by-slide content:
problem, solution, market size, traction, team, financials, and ask.

Commands (via chat):
  pitch outline    <company>       — full slide-by-slide outline
  pitch slide      <slide_name>    — detailed content for one slide
  pitch narrative  <company>       — investor narrative arc
  pitch financials <metrics>       — financial projections slide
  pitch full       <company>       — complete pitch deck document
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Venture Capital pitch coach who has reviewed 1000+ decks and helped founders raise $500M+. You know exactly what investors want to see.

Output JSON with this structure:
{
  "company_name": "...",
  "tagline": "One-liner value proposition",
  "investor_narrative": "The story arc in 3 sentences",
  "slides": [
    {
      "slide_number": 1,
      "title": "Cover / Title",
      "purpose": "What this slide must accomplish",
      "content": {
        "headline": "Slide headline",
        "body_points": ["bullet 1", "bullet 2"],
        "data_to_include": ["specific stat or metric"],
        "visual_suggestion": "What to show visually"
      },
      "investor_question_answered": "What investor question does this slide answer?",
      "common_mistakes": "What founders get wrong on this slide"
    }
  ],
  "market_sizing": {"tam": "...", "sam": "...", "som": "...", "methodology": "..."},
  "key_metrics": ["Most important metric 1", "metric 2"],
  "ask": {"amount": "...", "use_of_funds": [{"category": "...", "percent": 0}]},
  "strengths_to_emphasize": ["strength 1", "strength 2"],
  "red_flags_to_address": ["potential objection 1", "objection 2"]
}

Standard slides: Cover, Problem, Solution, Market Size, Business Model, Traction, Competition, Team, Financials, The Ask"""


class PitchDeckBuilderAgent(BaseAgent):
    agent_id = "pitch-deck-builder"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        company = payload.get("company") or payload.get("task", "")
        product = payload.get("product", "")
        market = payload.get("market", "")
        stage = payload.get("stage", "seed")
        ask_amount = payload.get("ask", "")
        traction = payload.get("traction", "")
        team = payload.get("team", "")

        prompt = (
            f"Build an investor pitch deck for:\n"
            f"Company: {company}\n"
            f"Product/Service: {product}\n"
            f"Market: {market}\n"
            f"Funding Stage: {stage}\n"
            f"Ask Amount: {ask_amount or 'TBD'}\n"
            f"Traction/Metrics: {traction or 'early stage'}\n"
            f"Team: {team or 'founding team'}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

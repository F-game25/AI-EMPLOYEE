"""Email Warmup Agent — email deliverability advisor.

Checks SPF/DKIM/DMARC configuration, estimates spam scores,
generates warmup sequence advice, and produces deliverability audit reports.

Commands (via chat):
  warmup check   <domain>    — full deliverability check
  warmup spf     <domain>    — SPF/DKIM/DMARC status
  warmup spam    <email>     — spam score estimation
  warmup plan    <domain>    — 30-day warmup sequence plan
  warmup report  <domain>    — complete deliverability audit
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are an Email Deliverability Expert with deep knowledge of DNS records, spam filters, and inbox placement.

Output JSON with this structure:
{
  "domain": "...",
  "overall_score": 0,
  "inbox_placement_estimate": "0%",
  "dns_checks": {
    "spf": {"status": "pass|fail|missing|neutral", "record": "...", "issues": [], "fix": "..."},
    "dkim": {"status": "pass|fail|missing", "selector": "...", "issues": [], "fix": "..."},
    "dmarc": {"status": "pass|fail|missing", "policy": "none|quarantine|reject", "issues": [], "fix": "..."}
  },
  "spam_indicators": [{"indicator": "...", "severity": "high|medium|low", "fix": "..."}],
  "warmup_plan": {
    "duration_days": 30,
    "phases": [
      {"days": "1-7", "daily_emails": 10, "strategy": "..."},
      {"days": "8-14", "daily_emails": 25, "strategy": "..."},
      {"days": "15-21", "daily_emails": 50, "strategy": "..."},
      {"days": "22-30", "daily_emails": 100, "strategy": "..."}
    ],
    "warmup_tips": ["tip 1", "tip 2"]
  },
  "blacklist_check": "Check these blacklists: MXToolBox, Spamhaus, Barracuda",
  "quick_wins": ["immediate action 1", "action 2"],
  "tools_recommended": ["MXToolBox", "Mail-Tester", "GlockApps", "Lemwarm"]
}"""


class EmailWarmupAgent(BaseAgent):
    agent_id = "email-warmup"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        domain = payload.get("domain") or payload.get("task", "")
        email_volume = payload.get("volume", "100/day")
        current_esp = payload.get("esp", "")
        has_dedicated_ip = payload.get("dedicated_ip", False)

        prompt = (
            f"Conduct a deliverability audit for:\n"
            f"Domain: {domain}\n"
            f"Target email volume: {email_volume}\n"
            f"Email Service Provider: {current_esp or 'not specified'}\n"
            f"Dedicated IP: {has_dedicated_ip}\n"
            f"Note: DNS checks are advisory — actual DNS lookup requires live tool access"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

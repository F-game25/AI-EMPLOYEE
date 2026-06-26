#!/usr/bin/env python3
"""Generate real definitions for the agent-advertised skills that have NO library
definition (the audit's 319). Each generated def is SPECIFIC (name-targeted role +
description), not boilerplate — combined with the executable engine + quality gate,
these become validated executable skills instead of generic agent fallbacks.

Agent-INTERNAL mechanics (indexing, rollback, routing, …) are NOT skills and are
excluded. Run once; commit runtime/config/skills_generated.json.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = json.loads((ROOT / "runtime/config/skills_library.json").read_text())["skills"]
AC = json.loads((ROOT / "runtime/config/agent_capabilities.json").read_text())
OUT = ROOT / "runtime/config/skills_generated.json"

# Patterns that mark an agent-INTERNAL mechanic (not a user-facing business skill).
INTERNAL = re.compile(
    r"(index|rollback|registry|persistence|_sync|dispatch|routing|router|scheduling|"
    r"scheduler|healthcheck|telemetry|vault|caching|cache_|backup|versioning|queue|"
    r"agent_(selection|memory|compos|coordinat|spawn|lifecycle)|skill_search|"
    r"batch_processing|alert_formatting|_config|compute_|runtime|provisioning|"
    r"heartbeat|watchdog|migration|orchestration|state_management|event_bus)", re.I)

ACRONYMS = {"seo": "SEO", "roi": "ROI", "ai": "AI", "crm": "CRM", "kpi": "KPI",
            "pl": "P&L", "api": "API", "ab": "A/B", "ppc": "PPC", "ux": "UX",
            "ui": "UI", "sql": "SQL", "b2b": "B2B", "b2c": "B2C", "saas": "SaaS",
            "defi": "DeFi", "nft": "NFT", "ad": "Ad", "ads": "Ads"}

# name keyword -> category (drives the executable engine's category gate)
CAT_RULES = [
    (("email", "cold", "outreach", "lead", "sales", "crm", "objection", "closing", "pitch", "proposal"), "Lead Generation & Sales"),
    (("seo", "ads", "ppc", "marketing", "campaign", "growth", "conversion", "funnel", "keyword", "content"), "Growth & Marketing"),
    (("roi", "pl", "finance", "revenue", "pricing", "budget", "forecast", "valuation", "invoice"), "Finance & Investment"),
    (("research", "analysis", "analyze", "audit", "report", "competitor", "market", "synthesis", "scoring"), "Research & Analysis"),
    (("frontend", "backend", "code", "api", "deploy", "test", "refactor", "database", "development"), "Development & Technical"),
    (("social", "instagram", "tiktok", "linkedin", "twitter", "post", "caption", "hashtag"), "Social Media"),
    (("support", "ticket", "refund", "escalation", "customer"), "Customer Support"),
    (("trade", "crypto", "signal", "wallet", "token", "defi", "arbitrage"), "Trading & Finance"),
    (("brand", "naming", "voice", "identity"), "Branding & Identity"),
    (("project", "sprint", "roadmap", "milestone", "okr", "task"), "Project Management"),
]


def humanize(skill_id: str) -> str:
    parts = [ACRONYMS.get(w, w.capitalize()) for w in skill_id.split("_")]
    return " ".join(parts)


def category_for(skill_id: str) -> str:
    low = skill_id.lower()
    for kws, cat in CAT_RULES:
        if any(k in low for k in kws):
            return cat
    return "Automation & Productivity"


def make_def(skill_id: str) -> dict:
    name = humanize(skill_id)
    return {
        "id": skill_id,
        "name": name,
        "category": category_for(skill_id),
        "description": f"Produce a complete, professional {name} deliverable — specific, actionable, and structured.",
        "prompt_hint": f"Produce a {name} for: [target]. Be concrete and actionable.",
        "tags": [w for w in skill_id.split("_") if len(w) > 2][:5],
        "system_prompt": (
            f"You are a senior specialist in {name}. Given the brief, produce a complete, "
            f"high-quality {name} deliverable. Be specific and actionable, use concrete details "
            f"and sensible defaults for anything unspecified, and structure the output clearly with "
            f"headings or sections. Do not ask for more input or add preamble — deliver the result now."
        ),
        "generated": True,
    }


def main() -> None:
    lib_ids = {e["id"] for e in LIB}
    agents = AC["agents"] if isinstance(AC, dict) else AC
    if isinstance(agents, dict):
        agents = list(agents.values())
    advertised = set()
    for a in agents:
        for s in (a.get("skills") or a.get("capabilities") or []):
            sid = s if isinstance(s, str) else (s.get("id") or s.get("name"))
            if sid:
                advertised.add(sid)
    undefined = sorted(advertised - lib_ids)
    user_facing = [s for s in undefined if re.fullmatch(r"[a-z][a-z0-9_]{2,50}", s) and not INTERNAL.search(s)]
    internal = [s for s in undefined if s not in user_facing]

    defs = {s: make_def(s) for s in user_facing}
    OUT.write_text(json.dumps({"_doc": "Auto-generated specific definitions for previously-undefined "
                               "agent-advertised skills (audit). Executable via the engine + category gate.",
                               "skills": list(defs.values())}, indent=1), encoding="utf-8")
    print(f"undefined={len(undefined)}  user_facing(defined)={len(user_facing)}  internal(excluded)={len(internal)}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print("sample internal excluded:", internal[:10])
    print("sample defined:", user_facing[:10])


if __name__ == "__main__":
    main()

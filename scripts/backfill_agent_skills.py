#!/usr/bin/env python3
"""Backfill the skill library so every skill an agent advertises is backed by a
real, executable definition.

Why: agents in ``runtime/config/agent_capabilities.json`` reference skill names
in their ``skills[]`` arrays, but only ~65 of ~435 referenced names had a
matching entry in ``runtime/config/skills_library.json``. The rest were labels
with no implementation — they could not be dispatched. ``catalog.py`` loads the
library by ``id`` into dispatchable skills, and (since 780b11a5) the
agent_controller / companion ``skills.run`` path executes a skill's
``system_prompt`` against the real LLM. So a referenced name is "usable" iff a
library entry exists whose ``id`` equals that name.

This generator finds every referenced name lacking an exact ``id`` match and
synthesizes a complete definition matching the existing 14-field schema,
including a domain-specific ``system_prompt``. It is catalog-driven (no
hardcoded skill list) and idempotent (existing ids are never overwritten or
duplicated), so it can be re-run whenever agents add new skill references.

Usage:
    python3 scripts/backfill_agent_skills.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPS_PATH = ROOT / "runtime" / "config" / "agent_capabilities.json"
LIB_PATH = ROOT / "runtime" / "config" / "skills_library.json"

# Agent category -> library category label (every label already exists in the
# library's `categories` list, so no new categories are introduced).
AGENT_CAT_TO_LIB_CAT = {
    "analytics": "Data Analysis",
    "coding": "Development & Technical",
    "communication": "Communication Channels",
    "content": "Content & Writing",
    "coordination": "Project Management",
    "creative": "Content & Writing",
    "crypto": "Crypto & Web3",
    "design": "Branding & Identity",
    "development": "Development & Technical",
    "ecommerce": "E-commerce & Product",
    "engineering": "Development & Technical",
    "finance": "Finance & Investment",
    "growth": "Growth & Marketing",
    "hr": "Company Building & Strategy",
    "infrastructure": "Development & Technical",
    "intelligence": "Research & Analysis",
    "management": "Project Management",
    "marketing": "Marketing & SEO",
    "operations": "Automation & Productivity",
    "orchestrator": "Automation & Productivity",
    "research": "Research & Analysis",
    "sales": "Lead Generation & Sales",
    "social": "Social Media",
    "strategy": "Company Building & Strategy",
    "support": "Customer Support",
    "testing": "Development & Technical",
    "trading": "Trading & Finance",
}
DEFAULT_LIB_CAT = "Automation & Productivity"

# Library category -> expert persona + domain guidance for the system prompt.
CAT_PROFILE = {
    "Content & Writing": ("expert content writer and editor", "Optimize for clarity, structure, and the target audience; include headings and a call-to-action where relevant."),
    "Research & Analysis": ("senior research analyst", "Cite the angles you considered, separate evidence from inference, and flag low-confidence claims."),
    "Trading & Finance": ("professional markets and trading analyst", "State assumptions, quantify risk, and never present speculation as certainty."),
    "Social Media": ("social media strategist", "Match the platform's format and algorithm, lead with a strong hook, and include relevant hashtags or CTAs."),
    "Lead Generation & Sales": ("B2B sales and lead-generation strategist", "Personalize to the ICP, lead with value, and end with a clear next step."),
    "Customer Support": ("senior customer support specialist", "Be empathetic and accurate; resolve the issue or escalate honestly rather than guessing."),
    "Development & Technical": ("senior software engineer", "Prefer correct, maintainable solutions; call out edge cases, security, and test implications."),
    "Data Analysis": ("data analyst", "Show the method, quantify findings, and translate numbers into a clear recommendation."),
    "E-commerce & Product": ("e-commerce and product specialist", "Tie recommendations to conversion, margin, and customer experience."),
    "Marketing & SEO": ("performance marketing and SEO strategist", "Ground recommendations in intent, search data, and measurable outcomes."),
    "Automation & Productivity": ("operations and automation specialist", "Define triggers, steps, and failure handling so the workflow is reproducible."),
    "Company Building & Strategy": ("company-building and strategy advisor", "Validate assumptions before recommending action; weigh trade-offs explicitly."),
    "Crypto & Web3": ("crypto and Web3 analyst", "Assess on-chain and protocol risk honestly; never present speculation as certainty."),
    "Finance & Investment": ("finance and investment analyst", "Be advisory-only, state assumptions, and quantify risk and downside."),
    "Branding & Identity": ("brand and identity designer", "Keep voice, visual system, and positioning consistent and ownable."),
    "Growth & Marketing": ("growth marketing strategist", "Design for measurable, compounding outcomes and clear success metrics."),
    "Project Management": ("project and delivery manager", "Make scope, owners, dependencies, and deadlines explicit."),
    "Growth Agency": ("growth agency operator", "Tie every deliverable to a client outcome and a measurable KPI."),
    "Conversion Optimization": ("conversion rate optimization specialist", "Form a hypothesis, define the metric, and prioritize by expected impact."),
    "Communication Channels": ("multi-channel communications specialist", "Adapt tone and format to the channel and confirm the intended action."),
    "Money Mode": ("revenue operations specialist", "Tie the action to real, measurable revenue impact — no fabricated numbers."),
    "Autonomy Governance": ("autonomy governance officer", "Enforce approval gates and surface risk before any consequential action."),
    "Wallet & Compute": ("wallet and compute operations specialist", "Treat funds and compute budgets as real; require explicit limits and consent."),
    "Supervised Finance Workflows": ("supervised finance workflow specialist", "Draft only; every output requires human sign-off before execution."),
    "AETERNUS Engineering Skills": ("principal engineer", "Hold a high bar for correctness, scalability, and security."),
}
DEFAULT_PROFILE = ("specialist", "Return a structured, verifiable result and state any missing context explicitly.")

# Tokens to render in a specific case when humanizing snake_case ids.
ACRONYMS = {
    "ai": "AI", "api": "API", "seo": "SEO", "sem": "SEM", "crm": "CRM", "roi": "ROI",
    "roas": "ROAS", "kpi": "KPI", "okr": "OKR", "ctr": "CTR", "cpa": "CPA", "cac": "CAC",
    "ltv": "LTV", "b2b": "B2B", "b2c": "B2C", "saas": "SaaS", "ui": "UI", "ux": "UX",
    "sql": "SQL", "css": "CSS", "html": "HTML", "url": "URL", "cta": "CTA", "llm": "LLM",
    "csv": "CSV", "pdf": "PDF", "qa": "QA", "kyc": "KYC", "gtm": "GTM", "icp": "ICP",
    "mql": "MQL", "sql_lead": "SQL", "faq": "FAQ", "sms": "SMS", "dm": "DM", "pr": "PR",
    "ppc": "PPC", "nft": "NFT", "defi": "DeFi", "tvl": "TVL", "p2p": "P2P", "kol": "KOL",
    "ab": "A/B", "swot": "SWOT", "moq": "MOQ", "sop": "SOP", "qbr": "QBR", "nps": "NPS",
}


def humanize(skill_id: str) -> str:
    toks = skill_id.split("_")
    # Common "a_b_*" family -> render the A/B prefix cleanly.
    if toks[:2] == ["a", "b"]:
        toks = ["ab"] + toks[2:]
    return " ".join(ACRONYMS.get(t, t.capitalize()) for t in toks)


def build_skill(skill_id: str, lib_cat: str, agents: list[str]) -> dict:
    title = humanize(skill_id)
    role, guidance = CAT_PROFILE.get(lib_cat, DEFAULT_PROFILE)
    tags = sorted({t for t in skill_id.split("_") if len(t) > 2})[:6] or [skill_id]
    return {
        "id": skill_id,
        "name": title,
        "category": lib_cat,
        "description": f"{title}: execute this capability end-to-end and return a structured, decision-ready result for {lib_cat} workflows.",
        "prompt_hint": f"Apply {title} to [subject] given [context]. Return the result, your rationale, and next steps.",
        "tags": tags,
        "compatible_agents": sorted(set(agents)),
        "input_format": {
            "required_fields": ["task_goal", "context", "constraints"],
            "optional_fields": ["examples", "priority", "deadline"],
            "input_contract": "Provide concise, verifiable context values. Reject empty or contradictory required fields.",
        },
        "output_format": {
            "sections": ["result", "rationale", "next_steps"],
            "format": "structured_markdown",
            "output_contract": "Every output must include a direct result, validation notes, and an actionable next step.",
        },
        "quality_standards": [
            "Output is complete and unambiguous",
            "Actionability is high",
            "Safety/compliance checks passed",
            f"{title}: produce deterministic, reproducible outputs for identical inputs.",
        ],
        "error_handling": {
            "retryable_errors": ["temporary_dependency_failure", "rate_limit", "timeout"],
            "non_retryable_errors": ["missing_context", "execution_failure", "validation_failure"],
            "fallback_strategy": "Return partial result with explicit gap report and escalation recommendation when full completion is impossible.",
        },
        "best_practices": [
            "Clarify ambiguity early",
            "Return structured outputs",
            "Document assumptions",
            f"State explicitly when required context for {title} is missing rather than inventing it.",
        ],
        "execution_steps": [
            f"Parse the goal, context, and constraints relevant to {title}.",
            f"Validate that required inputs for {title} are present; flag gaps before proceeding.",
            f"Apply {lib_cat} best practices to deliver {title}.",
            "Self-check the draft result against the quality standards and output contract.",
            "Return the result with rationale and concrete next steps.",
        ],
        "system_prompt": (
            f"You are a {role}. Your task is to apply the {title} capability to the provided goal, context, and constraints. "
            f"{guidance} Always return a structured, decision-ready result containing the key output, your rationale, "
            f"and concrete next steps. If required context is missing, say so explicitly instead of inventing it."
        ),
        "source": "agent_capability_backfill",
        "version": "1.0",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only; do not write")
    args = ap.parse_args()

    caps = json.loads(CAPS_PATH.read_text(encoding="utf-8"))["agents"]
    lib = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    skills = lib["skills"]
    existing_ids = {str(s.get("id")) for s in skills}

    referenced: dict[str, list[tuple[str, str]]] = {}
    for agent_id, v in caps.items():
        if not isinstance(v, dict):
            continue
        agent_cat = (v.get("category") or "").strip()
        for name in v.get("skills", []):
            referenced.setdefault(str(name), []).append((agent_id, agent_cat))

    missing = {name: meta for name, meta in referenced.items() if name not in existing_ids}

    new_entries = []
    for name in sorted(missing):
        meta = missing[name]
        agents = [a for a, _ in meta]
        # most-common library category among the referencing agents
        lib_cat = Counter(
            AGENT_CAT_TO_LIB_CAT.get(c, DEFAULT_LIB_CAT) for _, c in meta
        ).most_common(1)[0][0]
        new_entries.append(build_skill(name, lib_cat, agents))

    print(f"referenced skill names : {len(referenced)}")
    print(f"already backed (exact) : {len(referenced) - len(missing)}")
    print(f"generated definitions  : {len(new_entries)}")
    print(f"library total: {len(skills)} -> {len(skills) + len(new_entries)}")

    if args.dry_run:
        if new_entries:
            print("\nsample generated skill:\n" + json.dumps(new_entries[0], indent=2)[:1200])
        return 0

    skills.extend(new_entries)
    meta = lib.setdefault("_meta", {})
    meta["total_skills"] = len(skills)
    meta["updated_at"] = _dt.date.today().isoformat()
    meta["agent_capability_backfill"] = {
        "generated": len(new_entries),
        "method": "deterministic synthesis from agent_capabilities.json references (scripts/backfill_agent_skills.py)",
        "date": _dt.date.today().isoformat(),
    }
    LIB_PATH.write_text(json.dumps(lib, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {LIB_PATH.relative_to(ROOT)} (total_skills={len(skills)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

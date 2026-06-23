# Skill Batch 3 Production Upgrade

Date: 2026-06-23

## Summary

Batch 3 upgrades exactly 40 growth, reporting, finance, people-ops, planning,
communications, monitoring, and governance skills while preserving the canonical
library at 570 total skills. The upgraded skills are canonical replacements for
weak `agent_capability_backfill` entries in
`runtime/config/skills_library.json`. Each replacement keeps the old generated
ID as an alias so existing capability references continue resolving.

## Completed Skills

The batch covers growth marketing strategy, SEO opportunity auditing, technical
SEO, paid ads planning, ad copy review, conversion funnels, A/B test planning,
brand voice, social publishing pipelines, video scripts, topic and market
research, executive and daily reporting, financial report review, invoice and
payment follow-up planning, expense categorization, tax-prep checklists, unit
economics, budget guardrails, hiring role briefs, candidate screening support,
interview and onboarding plans, culture principles, OKR and milestone review,
stakeholder updates, RACI matrices, standup reports, Discord and WhatsApp
communication planning, message routing, web monitoring, threat-intelligence
briefs, tool policy review, and token budgeting.

All 40 skills include:

- production metadata and maturity status
- explicit use and non-use conditions
- required and optional inputs
- execution mode
- tool allow/deny lists
- safety level and approval requirement
- prompts and internal task template
- quality checklist, success criteria, failure modes, fallback strategy
- audit event names
- UI metadata with `wired: true`
- test cases

## Wiring

- Runtime catalog alias handling resolves replaced generated IDs to Batch 3
  canonical IDs.
- Skill selection scores Batch 3 production metadata such as `when_to_use`,
  aliases, tools, UI metadata, and internal task templates.
- The central skill registry treats Batch 3 aliases as coverage.
- Companion `skills.run` now describes growth, SEO, finance review, hiring,
  communication, monitoring, governance, and token budgeting routes.
- `/api/forge/skills` returns `batch1_count`, `batch2_count`, `batch3_count`,
  and `production_batch_count`.
- Forge skill panels render the same maturity, safety, approval, execution,
  tools, success criteria, test metadata, and `wired` state for Batch 3 skills.

## Safety Gates

Approval-gated Batch 3 skills include paid ads planning, social post pipelines,
video script drafting, invoice draft review, payment follow-up planning,
tax-prep checklist building, budget guardrails, hiring role briefs, candidate
screening assistance, stakeholder updates, Discord notification planning,
WhatsApp inbound triage, and tool policy review.

These skills prepare plans, drafts, reviews, or decision aids by default. They
must not publish, message, spend, send invoices, make hiring decisions, change
policy, modify accounts, or touch external systems without explicit human
approval.

## Verification Targets

- `tests/test_skill_batch1_readiness.py`
- `tests/test_skill_chain.py`
- `tests/test_skill_lifecycle.py`
- `tests/test_forge_skills_route.js`
- `frontend/src/__tests__/ForgeSkillsLibraryPane.test.jsx`

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
npm --prefix frontend run test -- src/__tests__/ForgeSkillsLibraryPane.test.jsx
npm --prefix frontend run build
```

## Remaining Work

Batch 4 now follows this same replacement-or-upgrade pattern. Future batches
should wait until the first 160 production skills are confirmed green in CI and
manually visible in the Forge dashboard against a live backend.

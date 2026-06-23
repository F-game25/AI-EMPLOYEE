# Skill Batch 2 Production Upgrade

Date: 2026-06-23

## Summary

Batch 2 upgrades exactly 40 Money Mode, client-work, operations, support, and
governance skills while preserving the canonical library at 570 total skills.
The upgraded skills are canonical replacements for weak
`agent_capability_backfill` entries in `runtime/config/skills_library.json`.
Each replacement keeps the old generated ID as an alias so existing capability
references continue resolving.

## Completed Skills

The batch covers opportunity discovery, paid-task evaluation, client brief
analysis, proposal and quote preparation, scope risk, deliverable packaging,
delivery review, earnings and feedback tracking, lead sourcing, ICP research,
prospect qualification, outreach, CRM planning, content operations, publishing
approval, affiliate and ecommerce evaluation, supplier risk, order and inventory
operations, marketplace listings, support triage, meeting and calendar planning,
workflow templates, automation runbooks, integration health, API key rotation,
secret exposure, tenant isolation, audit review, ROI, dashboard metrics, agent
performance, and learning dataset curation.

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

- Runtime catalog alias handling from Batch 1 resolves replaced generated IDs to
  Batch 2 canonical IDs.
- Skill selection scores Batch 2 production metadata such as `when_to_use`,
  aliases, tools, UI metadata, and internal task templates.
- The central skill registry treats Batch 2 aliases as coverage.
- `/api/forge/skills` now exposes any production batch, not only `batch_1`, and
  returns `batch1_count`, `batch2_count`, and `production_batch_count`.
- Forge skill panels already render maturity, safety, approval, execution,
  tools, success criteria, test metadata, and `wired` state for Batch 2 skills.

## Safety Gates

Approval-gated Batch 2 skills include proposal, quote, deliverable packaging,
earnings tracking, outreach, email personalization, CRM update planning,
publishing approval, marketplace listing optimization, support response review,
calendar scheduling, workflow template building, API key rotation, secrets
exposure checking, and learning dataset curation.

These skills prepare plans, drafts, reviews, or checks by default. They must not
publish, send, spend, write, change accounts, access wallets, rotate credentials,
or modify external systems without explicit human approval.

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

Batch 3 now follows this same replacement-or-upgrade pattern. Future batches
should wait until the first 120 production skills are confirmed green in CI and
manually visible in the Forge dashboard against a live backend.

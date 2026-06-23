# Skill Batch 4 Production Upgrade

Date: 2026-06-23

## Summary

Batch 4 upgrades exactly 40 integration, data pipeline, release operations,
observability, runtime resilience, knowledge-runtime, and agent-orchestration
skills while preserving the canonical library at 570 total skills. The upgraded
skills are canonical replacements for weak `agent_capability_backfill` entries
in `runtime/config/skills_library.json`. Each replacement keeps the old
generated ID as an alias so existing capability references continue resolving.

## Completed Skills

The batch covers API integration contracts, Shopify webhooks and inventory,
Shopify publish approval, Stripe and QuickBooks ingestion/reconciliation,
email/Twilio/Discord integrations, cross-channel notifications, data extraction
and export validation, CSV validation, batch jobs, cron schedules, backup and
archive readiness, deployment tracking, rollback review, patch rollout,
release versioning, changelogs, diagnostics, anomaly alert rules, system status,
agent coordination, selection, dispatch, composition, bot lifecycle, state
snapshots, multi-agent synthesis and coordination, provider fallback, session
persistence, vault index health, vault retrieval quality, trigger auditing, and
template quality scoring.

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

- Runtime catalog alias handling resolves replaced generated IDs to Batch 4
  canonical IDs.
- Skill selection scores Batch 4 production metadata such as `when_to_use`,
  aliases, tools, UI metadata, and internal task templates.
- The central skill registry treats Batch 4 aliases as coverage.
- Companion `skills.run` now describes integration, data pipeline, release,
  observability, runtime, vault, trigger, and multi-agent orchestration routes.
- `/api/forge/skills` returns `batch1_count`, `batch2_count`, `batch3_count`,
  `batch4_count`, and `production_batch_count`.
- Forge skill panels render maturity, safety, approval, execution, tools,
  success criteria, test metadata, and `wired` state for Batch 4 skills.

## Safety Gates

Approval-gated Batch 4 skills include Shopify inventory sync, Shopify publish
approval, Stripe data ingestion, QuickBooks sync reconciliation, Twilio
integration checks, cross-channel notifications, and rollback plan review.

These skills prepare checks, plans, audits, or decision aids by default. They
must not sync data, publish products, send notifications, perform rollbacks,
modify accounts, change credentials, or touch external systems without explicit
human approval.

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

Batch 5 now follows this same replacement-or-upgrade pattern. Future batches
should wait until the first 200 production skills are confirmed green in CI and
manually visible in the Forge dashboard against a live backend.

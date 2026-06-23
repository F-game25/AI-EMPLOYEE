# Skill Batch 1 Production Upgrade

Date: 2026-06-23

## Summary

Batch 1 upgrades exactly 40 high-impact system skills and keeps the canonical
library at 570 total skills. The upgraded skills are implemented as canonical
replacements for weak or generated entries in `runtime/config/skills_library.json`.
Each replacement keeps the old generated ID as an alias so existing agent
capability references can still resolve.

## Completed Skills

The batch covers codebase reading, architecture mapping, debugging, testing,
security, UI/UX, API/database inspection, agent planning, file-system planning,
browser research, source checking, documentation, prompt/context engineering,
memory/model routing, output judging, failure analysis, command safety, HITL
planning, compute planning, health checks, skill validation, dashboard sync, and
end-to-end execution planning.

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

- Runtime catalog resolves old IDs through aliases and exposes metadata to the
  dispatch path.
- Skill selection scores production metadata such as `when_to_use`,
  `tools_allowed`, aliases, UI metadata, and internal task templates.
- The central skill registry treats aliases as coverage so replaced generated
  IDs do not become false gaps.
- Companion `skills.run` now routes engineering, diagnostics, security,
  system-control, and dashboard-sync work into the shared skill chain.
- `/api/forge/skills` now returns global skill-library entries relevant to
  Forge/system work, with local Forge JSON skills kept as supplemental entries.
- Forge skill panels render canonical `id` and legacy `skill_id`, plus maturity,
  safety, approval, execution, tools, success criteria, and test metadata.

## Verification Targets

- `tests/test_skill_batch1_readiness.py`
- `tests/test_skill_chain.py`
- `tests/test_skill_lifecycle.py`
- `tests/test_forge_skills_route.js`
- `frontend/src/__tests__/ForgeSkillsLibraryPane.test.jsx`

## Follow-On Work

Batch 2 now follows this same replacement-or-upgrade pattern. Future batches
should avoid increasing skill count until the first 80 production skills stay
green in CI and are manually visible in the Forge dashboard against a live
backend.

# Skill Batch 7 Production Upgrade

Date: 2026-06-23

## Summary

Batch 7 upgrades exactly 40 runtime, security, research quality, finance,
legal, and governance skills while preserving the canonical library at 570 total
skills. The upgraded skills replace weak `agent_capability_backfill` entries in
`runtime/config/skills_library.json` and keep old IDs as aliases.

## Touched Skills

| Old ID | New canonical ID | Main change |
| --- | --- | --- |
| `agent_memory` | `agent_memory_health_checker` | Checks agent memory health and gaps. |
| `agent_skill_generation` | `skill_generation_planner` | Plans new skills before generation. |
| `ai_ml_engineering` | `ai_ml_implementation_reviewer` | Reviews AI/ML implementations. |
| `ai_powered_scanning` | `ai_scan_plan_builder` | Builds reviewable AI scan plans. |
| `chat_task_dispatch` | `chat_task_dispatch_reviewer` | Reviews chat-to-task dispatch. |
| `chatbot_design` | `chatbot_flow_reviewer` | Reviews chatbot flow quality. |
| `context_injection` | `context_injection_safety_reviewer` | Approval-gated context injection safety review. |
| `conversation_flows` | `conversation_flow_designer` | Designs structured conversation flows. |
| `cost_optimization` | `infrastructure_cost_optimizer` | Reviews runtime and infrastructure cost. |
| `coverage_analysis` | `coverage_gap_analyzer` | Finds test coverage gaps. |
| `devops_infrastructure` | `devops_infrastructure_reviewer` | Reviews DevOps infrastructure. |
| `python_development` | `python_implementation_planner` | Plans Python implementation work. |
| `security_audit` | `security_audit_planner` | Builds security audit plans. |
| `security_testing` | `security_test_plan_builder` | Builds security test plans. |
| `shell_exec` | `shell_command_execution_reviewer` | Approval-gated shell command review. |
| `prompt_scanning` | `prompt_injection_scan_planner` | Plans prompt-injection scans. |
| `long_term_memory` | `long_term_memory_policy_reviewer` | Reviews memory policy. |
| `memory_writeback` | `memory_writeback_reviewer` | Approval-gated memory writeback review. |
| `multi_stage_reasoning` | `multi_stage_reasoning_planner` | Plans multi-stage reasoning. |
| `task_routing` | `task_routing_policy_reviewer` | Reviews task routing policy. |
| `custom_agent_builder` | `custom_agent_spec_builder` | Builds custom agent specs. |
| `skill_search` | `skill_search_relevance_checker` | Checks skill search relevance. |
| `skill_gap_analysis` | `skill_gap_prioritizer` | Prioritizes skill gaps. |
| `defensive_osint` | `defensive_osint_brief_builder` | Builds defensive OSINT briefs. |
| `source_synthesis` | `source_synthesis_reviewer` | Reviews source synthesis quality. |
| `synthesis` | `synthesis_quality_reviewer` | Reviews synthesis quality. |
| `sec_filing_analysis` | `sec_filing_analysis_brief_builder` | Builds SEC filing analysis briefs. |
| `legal_review` | `legal_review_checklist_builder` | Approval-gated legal review checklist. |
| `contract_drafting` | `contract_draft_reviewer` | Approval-gated contract draft review. |
| `fundraising_prep` | `fundraising_readiness_reviewer` | Reviews fundraising readiness. |
| `investor_relations` | `investor_update_writer` | Approval-gated investor update drafting. |
| `valuation_methodology` | `valuation_methodology_reviewer` | Reviews valuation methodology. |
| `tax_calculation` | `tax_calculation_reviewer` | Approval-gated tax calculation review. |
| `payment_tracking` | `payment_tracking_reconciler` | Reconciles payment tracking state. |
| `payment_validation` | `payment_validation_reviewer` | Approval-gated payment validation review. |
| `invoicing` | `invoice_workflow_checker` | Checks invoice workflow. |
| `pnl` | `pnl_statement_reviewer` | Reviews PnL statements. |
| `pl_generation` | `profit_loss_draft_builder` | Builds profit/loss drafts. |
| `pl_projections` | `profit_loss_projection_reviewer` | Reviews profit/loss projections. |
| `daily_profit_alerts` | `daily_profit_alert_reviewer` | Reviews daily profit alert logic. |

## Wiring

- Runtime alias handling resolves replaced generated IDs to Batch 7 canonical IDs.
- Skill selection scores Batch 7 production metadata.
- The central skill registry treats Batch 7 aliases as coverage.
- Companion `skills.run` now includes runtime, command safety, prompt security,
  research quality, legal, contract, investor, tax, payment, invoice, and PnL
  routes.
- `/api/forge/skills` returns `batch1_count` through `batch7_count` plus
  `production_batch_count`.

## Safety Gates

Approval-gated Batch 7 skills include context injection safety, shell command
execution review, memory writeback, legal review checklists, contract review,
investor updates, tax calculation review, and payment validation review.

These skills prepare reviews, checklists, or plans by default. They must not run
shell commands, write memory, provide legal/tax final advice, validate payments,
send investor updates, or modify external systems without explicit human
approval.

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
npm --prefix frontend run test -- src/__tests__/ForgeSkillsLibraryPane.test.jsx
npm --prefix frontend run build
```

## Remaining Work

Do not plan Batch 8 until the first 280 production skills are confirmed green in
CI and manually visible in the Forge dashboard against a live backend.

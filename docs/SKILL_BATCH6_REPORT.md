# Skill Batch 6 Production Upgrade

Date: 2026-06-23

## Summary

Batch 6 upgrades exactly 40 productivity, project operations, company
operations, ecommerce, inventory, order, pricing, and growth research skills
while preserving the canonical library at 570 total skills. The upgraded skills
replace weak `agent_capability_backfill` entries in
`runtime/config/skills_library.json` and keep the old IDs as aliases.

## Touched Skills

| Old ID | New canonical ID | Main change |
| --- | --- | --- |
| `action_item_extraction` | `action_item_tracker` | Tracks action items with status, ownership, and follow-up gaps. |
| `note_creation` | `meeting_note_structurer` | Structures notes into useful meeting records. |
| `transcript_analysis` | `transcript_insight_extractor` | Extracts decisions, risks, and action items from transcripts. |
| `scheduling` | `schedule_conflict_planner` | Plans schedule changes with approval metadata. |
| `gantt_planning` | `gantt_timeline_reviewer` | Reviews timelines and dependency assumptions. |
| `work_breakdown_structure` | `work_breakdown_builder` | Produces actionable work breakdowns. |
| `progress_tracking` | `project_progress_reporter` | Reports project progress with validation notes. |
| `retrospective_facilitation` | `retrospective_action_planner` | Converts retrospectives into tracked improvements. |
| `team_coordination` | `team_coordination_brief_builder` | Builds coordination briefs and handoff notes. |
| `task_assignment` | `task_assignment_reviewer` | Reviews assignment ownership and workload risks. |
| `task_scheduling` | `task_schedule_optimizer` | Reviews task timing and sequencing. |
| `goal_management` | `goal_health_reviewer` | Reviews goal status and gaps. |
| `goal_decomposition` | `goal_decomposition_reviewer` | Checks whether goals are decomposed cleanly. |
| `workflow_design` | `workflow_design_reviewer` | Reviews workflow design and handoffs. |
| `workflow_generation` | `workflow_generation_planner` | Plans generated workflows before execution. |
| `workflow_management` | `workflow_management_auditor` | Audits workflow health and control points. |
| `company_management` | `company_operating_system_mapper` | Maps operating model and company routines. |
| `mission_tracking` | `mission_progress_tracker` | Tracks mission progress with evidence gaps. |
| `hierarchy_modeling` | `org_hierarchy_mapper` | Maps org hierarchy and authority assumptions. |
| `reporting_lines` | `reporting_line_reviewer` | Reviews reporting lines and ownership clarity. |
| `workload_tracking` | `workload_balance_checker` | Checks workload balance and capacity risk. |
| `amazon_research` | `amazon_product_researcher` | Performs grounded Amazon product research. |
| `marketplace_analysis` | `marketplace_competition_analyzer` | Analyzes marketplace competition with source notes. |
| `listing_automation` | `listing_automation_planner` | Plans listing automation with approval gates. |
| `supplier_api_integration` | `supplier_api_contract_reviewer` | Reviews supplier API contracts and payload assumptions. |
| `supplier_api_sync` | `supplier_api_sync_checker` | Checks supplier sync readiness with approval gates. |
| `low_stock_alerts` | `low_stock_alert_planner` | Plans low-stock alert rules. |
| `auto_reorder` | `auto_reorder_policy_reviewer` | Reviews auto-reorder policy before any buying action. |
| `order_routing` | `order_routing_rule_auditor` | Audits order routing rules. |
| `order_tracking` | `order_tracking_status_reporter` | Reports order tracking state. |
| `tracking_updates` | `shipment_tracking_update_writer` | Drafts shipment updates with approval metadata. |
| `price_comparison` | `price_comparison_researcher` | Compares prices with source and assumption notes. |
| `price_monitoring` | `price_monitoring_rule_planner` | Plans price monitoring rules. |
| `stock_monitoring` | `stock_monitoring_reporter` | Reports stock monitoring state. |
| `trend_detection` | `ecommerce_trend_detector` | Detects ecommerce trends with evidence notes. |
| `trend_spotting` | `trend_spotting_brief_builder` | Builds trend-spotting briefs. |
| `top_product_ranking` | `top_product_ranking_reviewer` | Reviews product ranking logic and evidence. |
| `product_design` | `product_design_brief_reviewer` | Reviews product design briefs. |
| `customer_segmentation` | `customer_segment_analyzer` | Analyzes customer segments and evidence gaps. |
| `niche_targeting` | `niche_targeting_reviewer` | Reviews niche targeting assumptions. |

## Wiring

- Runtime alias handling resolves replaced generated IDs to Batch 6 canonical IDs.
- Skill selection scores Batch 6 production metadata.
- The central skill registry treats Batch 6 aliases as coverage.
- Companion `skills.run` now includes productivity, project, company, ecommerce,
  inventory, order, pricing, and growth research routes.
- `/api/forge/skills` returns `batch1_count` through `batch6_count` plus
  `production_batch_count`.
- Forge skill panels render Batch 6 maturity, safety, approval, execution,
  tools, success criteria, test metadata, and `wired` state.

## Safety Gates

Approval-gated Batch 6 skills include schedule conflict planning, listing
automation planning, supplier API sync checking, auto-reorder policy review, and
shipment tracking updates.

These skills prepare reviews, plans, or drafts by default. They must not change
schedules, publish listings, sync suppliers, buy/reorder stock, send shipment
updates, or modify external systems without explicit human approval.

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
npm --prefix frontend run test -- src/__tests__/ForgeSkillsLibraryPane.test.jsx
npm --prefix frontend run build
```

## Remaining Work

Do not plan Batch 7 until the first 240 production skills are confirmed green in
CI and manually visible in the Forge dashboard against a live backend.

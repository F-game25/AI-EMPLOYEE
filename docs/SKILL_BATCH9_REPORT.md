# Skill Batch 9 Production Upgrade

Date: 2026-06-23

## Summary

Batch 9 upgrades exactly 40 weak `agent_capability_backfill` entries in
`runtime/config/skills_library.json` into production-ready skills, preserving the
canonical library at 570 total skills. Old IDs are kept as aliases so existing
agent references keep resolving. After batch 9 only 11 weak generated skills
remained (completed by batch 10).

This batch covers growth/marketing, content/social, research, finance, analytics,
ops, and engineering-review capabilities.

## Touched Skills

| Old ID | New canonical ID | Safety |
| --- | --- | --- |
| `lesson_writing` | `lesson_content_writer` | low |
| `linkedin_optimization` | `linkedin_profile_optimization_reviewer` | low |
| `list_segmentation` | `list_segmentation_planner` | medium |
| `market_entry_strategy` | `market_entry_strategy_reviewer` | medium |
| `market_positioning` | `market_positioning_reviewer` | low |
| `message_performance_tracking` | `message_performance_tracking_reporter` | low |
| `messaging_framework` | `messaging_framework_reviewer` | low |
| `meta_ads_strategy` | `meta_ads_strategy_reviewer` | medium |
| `mitigation_planning` | `risk_mitigation_plan_builder` | medium |
| `notifications` | `notification_dispatch_reviewer` | **high (approval)** |
| `order_aggregation` | `order_aggregation_reconciler` | medium |
| `outreach_sequencing` | `outreach_sequence_reviewer` | **high (approval)** |
| `performance_diagnosis` | `performance_diagnosis_analyst` | medium |
| `performance_prediction` | `performance_prediction_reviewer` | medium |
| `performance_tracking` | `performance_tracking_reporter` | low |
| `persona_creation` | `buyer_persona_builder` | low |
| `plg_strategy` | `plg_strategy_reviewer` | medium |
| `ppc_campaign_architecture` | `ppc_campaign_architecture_reviewer` | medium |
| `prediction_market_analysis` | `prediction_market_analysis_brief_builder` | medium |
| `price_prediction` | `price_prediction_review_brief_builder` | **high (approval)** |
| `profit_margin_calc` | `profit_margin_calculation_reviewer` | medium |
| `prospect_research` | `prospect_research_brief_builder` | medium |
| `quiz_generation` | `quiz_content_builder` | low |
| `report_generation` | `report_generation_reviewer` | medium |
| `rss_fetching` | `rss_feed_fetch_plan_builder` | low |
| `scene_extraction` | `scene_extraction_reviewer` | low |
| `schema_markup` | `schema_markup_reviewer` | low |
| `scripting` | `content_script_writer` | low |
| `self_improvement` | `self_improvement_proposal_reviewer` | medium |
| `seo_optimization` | `seo_optimization_reviewer` | low |
| `smart_contract_parameters` | `smart_contract_parameter_reviewer` | **high (approval)** |
| `storytelling` | `brand_storytelling_reviewer` | low |
| `strategic_analysis` | `strategic_analysis_brief_builder` | medium |
| `subscriber_management` | `subscriber_management_reviewer` | medium |
| `swarm_simulation` | `swarm_simulation_plan_reviewer` | medium |
| `thought_leadership` | `thought_leadership_content_reviewer` | **high (approval)** |
| `tiktok_scripting` | `tiktok_script_writer` | low |
| `tiktok_trend_scanning` | `tiktok_trend_scan_reporter` | low |
| `touchpoint_mapping` | `customer_touchpoint_map_builder` | low |
| `trading_bot_coding` | `trading_bot_code_reviewer` | **high (approval)** |

## Wiring

- `runtime/config/skills_library.json` — 40 canonical replacements applied by
  `scripts/upgrade_skill_batch9.py` (total preserved at 570, no duplicate IDs).
- `runtime/skills/batch1_readiness.py` — `BATCH9_SKILL_IDS` + `validate_batch9_library`.
- Runtime alias handling resolves replaced generated IDs to Batch 9 canonical IDs
  (generic `SkillRegistry` alias mechanism, no per-batch code).
- Skill selection scores Batch 9 production metadata (generic `skill_selector`).
- `/api/forge/skills` now returns `batch9_count` plus the rolling
  `production_batch_count` (auto-includes any `ui_metadata.batch`).
- Companion `skills.run` capability description + examples extended for the new
  domains.

## Safety Gates

Approval-gated Batch 9 skills: `notification_dispatch_reviewer`,
`outreach_sequence_reviewer`, `price_prediction_review_brief_builder`,
`smart_contract_parameter_reviewer`, `thought_leadership_content_reviewer`,
`trading_bot_code_reviewer`.

These skills prepare reviews, briefs, plans, or quality gates by default. They
must not send notifications/outreach, publish content, deliver financial/trading
signals, or change on-chain parameters without explicit human approval. No skill
executes shell commands, writes memory, trades, or contacts anyone directly.

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
```

Result: 55 pytest passed; node syntax OK; route test PASS.

## Follow-On

Batch 10 completes the campaign (final 11 skills). After batch 10 there are zero
weak `agent_capability_backfill` entries left in the library.

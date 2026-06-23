# Skill Batch 5 Production Upgrade

Date: 2026-06-23

## Summary

Batch 5 upgrades exactly 40 customer support, sales/outreach, content/design,
market monitoring, finance/trading review, and web research skills while
preserving the canonical library at 570 total skills. The upgraded skills are
canonical replacements for weak `agent_capability_backfill` entries in
`runtime/config/skills_library.json`. Each replacement keeps the old generated
ID as an alias so existing capability references continue resolving.

## Touched Skills

| Old ID | New canonical ID | Main change |
| --- | --- | --- |
| `customer_service` | `customer_service_workflow_planner` | Turns generic customer service into a support workflow planning skill. |
| `faq_handling` | `faq_knowledge_base_builder` | Converts FAQ handling into structured knowledge-base drafting and gap review. |
| `ticket_tracking` | `support_ticket_tracker` | Adds ticket-state tracking, assumptions, validation, and memory behavior. |
| `refund_processing` | `refund_case_reviewer` | Makes refunds review-only and approval-gated before any action. |
| `status_updates` | `customer_status_update_writer` | Produces customer-facing status drafts with approval metadata. |
| `customer_notification` | `customer_notification_approval_planner` | Adds explicit approval planning for outbound customer notifications. |
| `lead_generation` | `lead_generation_campaign_planner` | Turns lead generation into a grounded campaign planning workflow. |
| `lead_hunting` | `lead_hunting_researcher` | Adds source-aware prospect research and validation behavior. |
| `lead_enrichment` | `lead_enrichment_validator` | Validates enriched lead data instead of accepting generated records. |
| `icp_matching` | `icp_match_score_reviewer` | Reviews ICP fit scoring with explicit criteria and gaps. |
| `icp_scoring` | `icp_scoring_model_reviewer` | Reviews scoring models and qualification criteria. |
| `cold_outreach` | `cold_outreach_risk_reviewer` | Adds safety/compliance review before outbound outreach. |
| `cold_email_writing` | `cold_email_draft_reviewer` | Makes cold email drafting review-only and approval-gated. |
| `cold_email_sequences` | `cold_email_sequence_planner` | Plans cadence and risks without sending messages. |
| `email_deliverability` | `email_deliverability_checker` | Adds deliverability checks and blocked-action reporting. |
| `email_campaigns` | `email_campaign_approval_planner` | Adds approval gates before campaign sends. |
| `open_rate_optimisation` | `open_rate_experiment_analyzer` | Converts open-rate optimization into experiment analysis. |
| `sales_forecasting` | `sales_forecast_reviewer` | Reviews sales forecasts and assumptions. |
| `pipeline_management` | `sales_pipeline_health_checker` | Adds sales pipeline health checks and reporting. |
| `spam_analysis` | `spam_risk_analyzer` | Reviews spam/compliance risk for outreach. |
| `content_strategy` | `content_strategy_brief_builder` | Produces structured content strategy briefs. |
| `copywriting_expert` | `copywriting_quality_reviewer` | Reviews copy quality against explicit criteria. |
| `sales_copy` | `sales_copy_reviewer` | Reviews sales copy for clarity, risk, and conversion intent. |
| `script_writing` | `script_outline_builder` | Turns script writing into outline-first planning. |
| `voiceover_generation` | `voiceover_script_reviewer` | Reviews voiceover scripts with approval metadata. |
| `image_prompt_generation` | `image_prompt_quality_reviewer` | Reviews image prompts for quality and constraints. |
| `visual_prompts` | `visual_prompt_art_director` | Adds art-direction structure for visual prompts. |
| `design_system_creation` | `design_system_auditor` | Reviews design-system consistency instead of generating labels. |
| `responsive_layout` | `responsive_layout_checker` | Adds responsive layout checks and validation guidance. |
| `ui_audit` | `ui_quality_issue_finder` | Finds UI quality issues with structured output. |
| `market_monitoring` | `market_monitoring_brief_builder` | Builds market monitoring briefs with source and risk notes. |
| `signal_aggregation` | `trading_signal_aggregator` | Aggregates signals as approval-gated research, not trading advice. |
| `signal_generation` | `trading_signal_quality_reviewer` | Reviews signal quality and blocks execution claims. |
| `backtesting` | `backtest_plan_reviewer` | Reviews backtest plans before implementation. |
| `portfolio_tracking` | `portfolio_tracking_reporter` | Reports portfolio tracking state with assumptions. |
| `portfolio_optimization` | `portfolio_optimization_risk_reviewer` | Reviews optimization risk and requires approval before action. |
| `financial_analysis` | `financial_analysis_brief_builder` | Builds finance research briefs with caveats and validation. |
| `web_search` | `web_search_plan_builder` | Plans web research queries and source strategy. |
| `web_fetch` | `web_fetch_safety_reviewer` | Reviews external fetch safety and source boundaries. |
| `fact_verification` | `fact_checking_workflow_runner` | Runs a structured fact-checking workflow with evidence gaps. |

## Wiring

- Runtime catalog alias handling resolves replaced generated IDs to Batch 5
  canonical IDs.
- Skill selection scores Batch 5 production metadata such as `when_to_use`,
  aliases, tools, UI metadata, and internal task templates.
- The central skill registry treats Batch 5 aliases as coverage.
- Companion `skills.run` now describes customer support, sales/outreach,
  content/design, finance/trading review, web research, and fact-check routes.
- `/api/forge/skills` returns `batch1_count` through `batch5_count` plus
  `production_batch_count`.
- Forge skill panels render maturity, safety, approval, execution, tools,
  success criteria, test metadata, and `wired` state for Batch 5 skills.

## Safety Gates

Approval-gated Batch 5 skills include refund review, customer status updates,
customer notification planning, cold outreach review, cold email review, cold
email sequences, email campaign approval, voiceover script review, trading signal
aggregation, trading signal quality review, and portfolio optimization risk
review.

These skills prepare plans, reviews, drafts, or decision aids by default. They
must not contact customers or leads, send campaigns, issue refunds, publish
content, execute trades, rebalance portfolios, or modify external systems without
explicit human approval.

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
npm --prefix frontend run test -- src/__tests__/ForgeSkillsLibraryPane.test.jsx
npm --prefix frontend run build
```

## Remaining Work

Batch 6 now follows this same replacement-or-upgrade pattern. Future batches
should wait until the first 240 production skills are confirmed green in CI and
manually visible in the Forge dashboard against a live backend.

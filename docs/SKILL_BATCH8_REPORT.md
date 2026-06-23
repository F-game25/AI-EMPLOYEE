# Skill Batch 8 Production Upgrade

Date: 2026-06-23

## Summary

Batch 8 upgrades exactly 40 content, growth, brand, sales, analytics, people,
customer, and operations skills while preserving the canonical library at 570
total skills. The upgraded skills replace weak `agent_capability_backfill`
entries in `runtime/config/skills_library.json` and keep old IDs as aliases.

## Touched Skills

| Old ID | New canonical ID | Main change |
| --- | --- | --- |
| `a_b_testing_emails` | `email_ab_test_analyzer` | Reviews email experiment results and evidence gaps. |
| `ab_testing_framework` | `growth_ab_test_plan_reviewer` | Reviews growth experiment plans. |
| `accessibility_audit` | `accessibility_audit_checker` | Checks accessibility audit findings and WCAG gaps. |
| `alert_formatting` | `trading_alert_format_reviewer` | Approval-gated trading alert format review. |
| `audit_trail` | `customer_audit_trail_reviewer` | Reviews customer/support audit history. |
| `brand_positioning` | `brand_positioning_reviewer` | Reviews positioning statements and market fit. |
| `budget_allocation` | `marketing_budget_allocation_reviewer` | Reviews marketing budget allocation. |
| `campaign_ideation` | `campaign_idea_brief_builder` | Builds campaign idea briefs. |
| `campaign_scheduling` | `campaign_schedule_planner` | Plans campaign launch calendars. |
| `candidate_outreach` | `candidate_outreach_message_reviewer` | Approval-gated recruiting outreach review. |
| `color_palette_design` | `color_palette_system_reviewer` | Reviews brand color palette systems. |
| `comment_automation` | `comment_automation_safety_reviewer` | Approval-gated social comment automation review. |
| `compensation_benchmarking` | `compensation_benchmark_brief_builder` | Builds compensation benchmark briefs. |
| `competitive_brand_analysis` | `competitive_brand_analysis_reviewer` | Reviews competitive brand analysis. |
| `component_specification` | `component_spec_writer` | Writes reviewable UI component specs. |
| `content_curation` | `content_curation_planner` | Plans curated content workflows. |
| `content_generation` | `social_content_generation_reviewer` | Reviews generated social content. |
| `conversion_optimization` | `conversion_optimization_planner` | Plans CRO work and validation. |
| `conversion_tracking` | `conversion_tracking_checker` | Checks conversion tracking plans and proof. |
| `cost_tracking` | `operating_cost_tracking_reviewer` | Reviews operating cost tracking. |
| `crypto_community_building` | `crypto_community_growth_planner` | Plans Web3 community growth. |
| `dark_mode_design` | `dark_mode_accessibility_reviewer` | Reviews dark theme contrast and accessibility. |
| `data_analysis` | `data_analysis_plan_reviewer` | Reviews data analysis methodology. |
| `deliverability_optimization` | `email_deliverability_optimization_checker` | Checks email deliverability optimization plans. |
| `developer_handoff` | `developer_handoff_package_reviewer` | Reviews design-to-dev handoff packages. |
| `dns_verification` | `dns_verification_checklist_builder` | Builds SPF/DKIM/DMARC verification checklists. |
| `document_generation` | `document_generation_reviewer` | Reviews generated documents for quality and evidence. |
| `drip_sequences` | `drip_sequence_planner` | Plans drip email sequences. |
| `earnings_quality` | `earnings_quality_reviewer` | Reviews earnings quality analysis. |
| `email_composition` | `email_composition_reviewer` | Approval-gated email draft review. |
| `email_sequence` | `email_sequence_planner` | Plans multi-email campaign sequences. |
| `engagement_tracking` | `engagement_tracking_reporter` | Reports engagement tracking quality. |
| `follow_up_automation` | `follow_up_automation_planner` | Plans follow-up automation without sending. |
| `follow_up_generation` | `follow_up_message_writer` | Approval-gated follow-up message drafting. |
| `follow_up_sequencing` | `follow_up_sequence_reviewer` | Reviews follow-up cadence and risk. |
| `image_prompt_creation` | `image_prompt_brief_builder` | Builds visual prompt briefs. |
| `image_prompts` | `image_prompt_safety_reviewer` | Reviews visual prompt safety and specificity. |
| `improvement_proposals` | `improvement_proposal_prioritizer` | Prioritizes improvement proposals. |
| `interview_scheduling` | `interview_schedule_planner` | Plans candidate interview schedules. |
| `keyword_search` | `keyword_search_plan_builder` | Builds keyword search plans. |

## Wiring

- Runtime alias handling resolves replaced generated IDs to Batch 8 canonical IDs.
- Skill selection scores Batch 8 `when_to_use`, alias, tool, UI, and task-template metadata.
- The central skill registry treats Batch 8 aliases as coverage.
- Companion `skills.run` now advertises growth, content, brand, accessibility,
  sales follow-up, deliverability, DNS, image prompt, keyword, and improvement
  proposal domains.
- `/api/forge/skills` returns `batch1_count` through `batch8_count` plus
  `production_batch_count`.

## Safety Gates

Approval-gated Batch 8 skills include trading alert formatting, candidate
outreach, comment automation, email composition, and follow-up message writing.

These skills prepare reviews, briefs, or drafts by default. They must not send
emails, contact candidates, publish content, automate social comments, deliver
trading/investment messages, or modify external systems without explicit human
approval.

## Verification Commands

```bash
PYTHONPATH=runtime python3 -m pytest tests/test_skill_batch1_readiness.py tests/test_skill_chain.py tests/test_skill_lifecycle.py
node --check backend/routes/forge.js backend/ascendforge/engine.js
node tests/test_forge_skills_route.js
npm --prefix frontend run test -- src/__tests__/ForgeSkillsLibraryPane.test.jsx
npm --prefix frontend run build
git diff --check
```

## Remaining Work

Do not start Batch 9 until Batch 8 is pushed as its own GitHub checkpoint and
the first 320 production skills remain green in local verification.

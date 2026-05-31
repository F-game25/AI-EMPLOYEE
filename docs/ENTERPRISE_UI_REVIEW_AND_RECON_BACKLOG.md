# Enterprise UI Review And Recon Backlog

## Baseline

This review is based on the current dashboard route inventory:

- Nexus Dashboard
- Cognition
- Agents
- Memory
- Economy
- Tasks / Operations
- Workflows
- AscendForge
- Neural Graph
- Knowledge
- Research
- Recon
- Security
- Models
- Integrations
- System / Runtime
- Settings
- Workspace

The enterprise rule is: pages must use real data, explicit empty states, explicit degraded states, or visibly labeled representative data. Hidden live-looking stubs are not acceptable.

## Recon

Current upgrade:

- Add a first-class `ReconPage`.
- Use `/api/recon/*` instead of exposing raw security-tool internals.
- Keep Recon scoped to safe OSINT and defensive local analysis.
- Store cases, findings, and audit events in local state.
- Keep Research separate from Recon.

Required next work:

- Add case detail drawer with linked findings, tool runs, notes, and exports.
- Add finding review workflow: open, accepted, false positive, remediated.
- Add approval request flow for passive network-backed lookups.
- Add export to Knowledge, Memory, Task, or Workflow.
- Add screenshots/attachments for evidence.

## Nexus Dashboard

Needs:

- One backend avatar state contract for active subsystem, memory activity, model calls, task/workflow activity, security state, degraded reasons, and current objective.
- Idle visuals should be mostly static; active visuals should move only around real events.
- Reduce visual clutter and keep black/gold/bronze as the dominant theme.
- Every metric card should show source and freshness.
- Add “why degraded” drilldown from the main status.

## Cognition

Needs:

- Real cognition trace: classify, retrieve, plan, tool decision, validate, execute, memory writeback.
- Decision detail drawer with selected option, rejected alternatives, confidence, policy gate, and source memory.
- Learning panel tied to real task outcomes.
- A/B tests must be executable and measurable, not only listable.
- Promote successful patterns to Workflows.

## Agents

Needs:

- Normalize live agents, manifest agents, and AscendForge-created agents into one UI shape.
- Fix visual glitches and overflow in cards.
- Add detail drawer: job description, skills, hooks, workflows, tools, model profile, memory policy, verification commands.
- Add controls: assign task, pause/resume, inspect logs, open in AscendForge, retire with approval.
- Show real health, current task, success rate, cost, and recent errors.

## Memory

Needs:

- Keep three workspaces: Personal Facts, Conversation History, Semantic Store.
- Add source provenance for every memory item.
- Add relationship viewer and graph links.
- Add merge duplicates, mark wrong, pin, forget, and reindex actions.
- Connect memory objects to the Neural Graph page.

## Economy

Needs:

- Remove live-looking demo metrics.
- Show real ledger, wallet state, token/API costs, task value, pipeline value, compute quotes, and approvals.
- Add owner approval gates for claim, spend, external compute, and delivery.
- Add historical charts only when history exists.

## Tasks / Operations

Needs:

- Board, list, create task, scheduler, task detail, history, approvals.
- Scheduler must support create, edit, pause, resume, run now, delete.
- Task detail must include trace, logs, artifacts, agent, workflow, retries, and approvals.
- Add SLA/priority filters and queue health.

## Workflows

Needs:

- Live canvas must show real workflow executions.
- Template cards must expand with steps, inputs, outputs, agents, skills, risks, estimated cost.
- Use Template must create a draft workflow.
- Skill Packs must load real skills from the skills library.
- Finance templates must run as draft-only workflows.
- Builder must create persisted workflow definitions.

## AscendForge

Needs:

- Keep AscendForge as supervised code/build subsystem, not the main AI.
- Add project selection, plan, file diff, actions, tests, snapshots, approval queue.
- Route code-changing work through policy, sandbox validation, and approval.
- Persist sessions, plans, actions, approvals, test results, and snapshots.
- Created agents/tools/skills/workflows must register into the existing system after approval.

## Neural Graph

Needs:

- Four graph views: Overview, Memory, Cognition, Operations.
- Graphs must use real backend read models.
- Idle graphs should be static.
- Activity events should animate only relevant nodes and edges.
- Add node inspector, edge inspector, source links, filters, search, path isolation, and degraded states.
- Remove fake active connection rows.

## Knowledge

Needs:

- Improve note detail/editor ergonomics.
- Add backlinks, graph links, broken link repair, and source provenance.
- Export notes to semantic memory.
- Link notes to related tasks, workflows, and agents.

## Research

Needs:

- Keep Research for knowledge discovery and source synthesis.
- Add source credibility scoring, citation quality, and export to Knowledge/Memory/Task.
- Show research run history and cost.
- Add comparison table for selected sources.

## Security

Needs:

- Keep Security focused on threat console, gateway events, blocked IPs, anomaly findings, audit/compliance, HITL approvals, and security engine status.
- Remove hidden stub threat/audit/HITL data.
- Every dangerous action must require confirmation and audit.
- Recon tool running belongs on Recon, not Security.

## Models

Needs:

- Remove stub performance/routing/prompt data.
- Show real provider readiness, model availability, local/offline status, cost, latency, and token usage.
- Add routing rule editor with validation, rollback, and policy labels.
- Add model download/install state for offline-first local models.

## Integrations

Needs:

- Replace stub webhooks with real hook status.
- Mobile pairing needs trust state, revoke, last seen, transport, and device audit.
- Every connector must show disabled/offline/policy-gated when unavailable.
- Add per-connector logs and test result history.

## System / Runtime

Needs:

- Replace static process/container/patch/log data with real diagnostics.
- Add resource history, launcher/runtime identity, packaged resource status, Python/Node process ownership, and port ownership.
- Add diagnostics bundle export.
- Separate app startup, runtime process, dashboard route, and degraded AI subsystem failures.

## Settings

Needs:

- Verify every control persists to a real backend setting.
- Add “requires restart,” “policy-gated,” and “offline-only” labels.
- Red-zone actions require typed confirmation and audit.
- Add settings import/export with secret redaction.

## Workspace

Needs:

- Improve file browsing, ingestion logs, analysis results, and artifact previews.
- Add project scope and safe path indicators.
- Link files to Memory, Knowledge, and AscendForge plans.
- Add file provenance and ingestion status.

## Cross-Page Standards

- Every page has loading, empty, degraded, permission-required, and approval-required states.
- Every page exposes source and freshness for key data.
- No fake data may look live.
- Every mutating action needs success/error feedback.
- High-risk actions need audit.
- Mobile layouts must be usable, not just compressed desktop layouts.
- Text must not overflow cards, buttons, tabs, or drawers.

## Acceptance Tests To Add

- Route smoke test for every page.
- Recon safe catalog test: no banned categories or IDs.
- Security page test: no recon runner in operational security view.
- Empty backend test for every enterprise page.
- Degraded backend test for every enterprise page.
- Screenshot checks for desktop and mobile widths.
- Build check with `npm --prefix frontend run build`.

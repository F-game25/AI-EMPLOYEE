# AETERNUS NEXUS Fork Enrichment Roadmap

## Purpose

CashClaw, Automaton, Financial Services, and Agent Skills are enhancement sources for the existing AETERNUS NEXUS architecture. They must not become separate apps, external extensions, or replacement runtimes.

The system now has native contracts for:

- engineering skill recommendation
- supervised finance workflows
- Money Mode task lifecycle
- autonomy policy and tool risk evaluation
- owner-controlled wallet vault
- local channel/session routing
- vendor intake verification

## Current Native Entry Points

### Backend APIs

- `GET /api/vendor/sources`
- `POST /api/skills/recommend`
- `GET /api/finance/workflows`
- `POST /api/finance/workflows/:id/run`
- `POST /api/finance/workflows/:runId/approve`
- `GET /api/money/tasks`
- `POST /api/money/tasks/:id/evaluate`
- `POST /api/money/tasks/:id/quote-draft`
- `POST /api/money/tasks/:id/deliver`
- `POST /api/money/feedback`
- `GET /api/autonomy/policy`
- `POST /api/autonomy/tool-call/evaluate`
- `GET /api/autonomy/heartbeat`
- `POST /api/autonomy/heartbeat/task`
- `GET /api/wallet/status`
- `POST /api/wallet/create`
- `POST /api/wallet/claim-request`
- `POST /api/wallet/compute-purchase/quote`

### UI Entry Points

- Workflows: imported skill packs and finance draft workflows.
- Money Mode: internal task inbox, owner wallet vault, approval gates.
- AscendForge: autonomy policy preview for pending actions.

## Phase 1: Make The Enhancement Layer Persistent

Goal: replace in-memory run/task state with existing storage and audit patterns.

Tasks:

- Store finance workflow runs in the existing database/state layer.
- Store Money Mode task evaluations, quotes, approvals, deliveries, and feedback.
- Store autonomy policy decisions in an audit table/log.
- Store wallet vault audit events in the existing observability/audit surface.
- Add tenant/user ownership fields where tenancy is enabled.

Acceptance:

- Restarting the app does not lose workflow runs, quotes, or approval history.
- Every dangerous action has a traceable owner approval record.

## Phase 2: Connect Agents And Skills

Goal: agents can actually use the imported skill/workflow metadata.

Tasks:

- Add imported engineering skills to AscendForge project planning.
- Let AscendForge attach skill packs before generating a plan.
- Add skill recommendations to agent task creation.
- Add finance workflows as supervised agent job templates.
- Route all file writes, shell commands, delivery actions, tool installs, and agent creation through `/api/autonomy/tool-call/evaluate`.

Acceptance:

- A project plan shows selected skills, verification gates, and policy risk before execution.
- Dangerous actions cannot bypass approval.

## Phase 3: Money Mode Becomes Operational

Goal: Money Mode manages work from opportunity to approved delivery. it needs to do real world execution

Tasks:

- Add task source adapters for internal tasks first.
- Add external marketplace adapters only behind policy and pairing.
- Build quote builder UI with complexity, hours, revisions, and risk.
- Add deliverable preview and approval queue.
- Add feedback ingestion into memory.
- Add earnings ledger linked to wallet vault balance.

Acceptance:

- The system can discover or create a task, evaluate it, draft a quote, prepare work, request approval, and mark it delivered.
- No external delivery or payment movement occurs without owner approval.

## Phase 4: Owner Wallet And External Compute

Goal: the system can hold owner-controlled earnings and request approved external compute purchases.

Tasks:

- Finish encrypted local wallet vault UI: create, backup warning, claim request, audit history.
- Add provider policy for external compute vendors.
- Add quote-only compute purchase flow.
- Add daily/monthly spend limits.
- add one click approval and execution
- Add owner approval ceremony before purchase execution.
- Keep autonomous spending blocked permanently unless owner policy explicitly changes.
- this need to be a fully functional selfbuild safe wallet which can send and accept money/crypto
Acceptance:

- Wallet creation requires owner approval and a strong passphrase.
- External compute purchase is disabled by default and can only execute from agent code directly when owner approved
- wallet is fully functional and safe

## Phase 5: Finance Workflow Hardening

Goal: finance features are useful but supervised.

Tasks:

- Add source document upload/linking.
- Add draft output viewer.
- Add review checklist: source coverage, assumption risk, compliance notes.
- Add "approved for internal use" and "export blocked until approved" states.
- Add clear non-advice and no-transaction semantics in API and UI.

Acceptance:

- Finance workflows never post ledgers, execute trades, or move funds.
- Every generated finance output is a draft until reviewed.

## Phase 6: UI Review And Improvements

Goal: integrate the new features into the existing premium command center without clutter and with working features and systems

### Workflows Page

Current improvement:

- Shows native capability packs, skill recommendation, and finance workflow templates.

Next improvements:

- Add tabs: `Live Canvas`, `Templates`, `Skill Packs`, `Finance`.
- Show each workflow's backing APIs and readiness state.
- Add "Create Job From Template" with approval policy preview.

### Money Mode Page

Current improvement:

- Shows task inbox, wallet vault state, and approval gates.

Next improvements:

- Add task detail drawer: evaluate, quote draft, deliverable preview, approval status.
- Add wallet setup modal with owner approval and backup warning.
- Add earnings ledger with pending/available/claimed funds.
- Add compute quote panel, disabled until policy enables it.

### AscendForge Page

Current improvement:

- Shows autonomy policy preview for pending actions.

Next improvements:

- Add skill pack selector before a project plan is generated.
- Add policy decision labels directly on each action row.
- Add "why approval is required" detail for dangerous actions.
- Add generated agent/skill/tool creation flows guarded by policy.

### Agents Page

Next improvements:

- Show imported capability packs attached to agents.
- Add job descriptions, hooks, risk level, and workflow templates per agent.
- Add "create agent with AscendForge" path using skill packs and autonomy policy.

### Knowledge/Memory Pages

Next improvements:

- Show finance sources, task feedback, skill usage, and policy audit as searchable memory objects.
- Add filters for `finance`, `money`, `autonomy`, `skills`, and `wallet`.

### Integrations Page

Next improvements:

- Show local channel as live.
- Show external messaging/marketplace providers as disabled by default with policy requirements.
- Add pairing and allowlist UI only after provider adapter exists.

## Phase 7: Enterprise Verification

Tasks:

- Add tests for vendor intake manifest validation.
- Add backend route tests for skills, finance, money, autonomy, wallet.
- Add frontend smoke tests for Workflows, Money Mode, and AscendForge enrichment panels.
- Extend package verification to require fork integration manifest and vendor manifests.

Commands:

- `python3 scripts/verify_vendor_intake.py`
- `python3 scripts/verify_core_dependencies.py`
- `npm --prefix frontend run build`
- `npm --prefix launcher run verify`
- `npm run package:enterprise:linux`

## Security Rules

- Imported fork content must be renamed, checksummed, licensed, and mapped to native AETERNUS modules.
- No autonomous wallet spending.
- No autonomous external compute purchase.
- No external marketplace delivery without owner approval.
- No finance output can be treated as investment advice or transaction execution.
- No self-replication, domain purchase, external compute purchase, or uncontrolled self-modification.

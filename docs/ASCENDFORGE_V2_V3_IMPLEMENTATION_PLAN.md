# AscendForge V2/V3 Implementation Plan

This plan grounds V2/V3 in the currently implemented V1 run flow. It is not a
replacement architecture. It is the migration path from the existing supervised
Forge contract to durable storage, isolated execution, multi-agent review, and
measurable quality gates.

## Current V1 Baseline

Canonical V1 lives in `backend/routes/forge.js` and is mounted at
`/api/forge` before the legacy inline Forge handlers in `backend/server.js`.

Implemented run contract:

1. `POST /api/forge/runs`
   - Requires auth.
   - Accepts `project_id`, `goal`, optional `provider`, `mode`,
     `max_iterations`, and context options.
   - Builds a context pack from project tree, recent sessions, code-index
     summary, and retrieved code chunks.
   - Creates a plan with skills, impacted files, approvals, verification
     commands, and rollback strategy.
   - Calls the Python chat backend, with local Ollama fallback, to generate
     code-block proposals.
   - Extracts write actions and policy-checks each patch.
   - Persists a run containing `context_pack`, `plan`, `actions`, `patches`,
     `approvals`, `test_results`, `review`, `final_report`, and
     `workspace_path`.

2. `POST /api/forge/runs/:id/approve`
   - Requires explicit owner approval.
   - Stages approved write actions into a copied workspace under
     `state/forge/runs/{run_id}/workspace`.
   - Updates action and patch status to `staged` or `blocked`.
   - Records approvals and audit events.

3. `POST /api/forge/runs/:id/verify`
   - Requires explicit owner approval.
   - Runs allowlisted build/test/lint/typecheck commands inside the staged
     workspace.
   - Appends a `test_results` record and moves the run to `verified` or
     `verify_failed`.

4. `POST /api/forge/runs/:id/apply`
   - Requires explicit owner approval.
   - Requires the latest verification to pass unless forced.
   - Blocks policy-denied patches.
   - Copies verified staged files back into the project root.
   - Creates per-file snapshots under `.forge_snapshots`.
   - Writes a `final_report` with applied files, snapshots, test result, and
     next steps.

Supporting V1 surfaces:

- `/api/forge/projects`, `/api/forge/files/*`, `/api/forge/index`,
  `/api/forge/context`, `/api/forge/summary/:projectId`.
- `/api/forge/agentic-run`, a bounded staged generation and verification loop
  that still requires approval before live apply.
- `runtime/core/code_indexer.py`, a dedicated per-project code index stored
  under `state/code_index`.
- `backend/ascendforge/engine.js`, the thin skill/blueprint engine.
- Legacy compatibility handlers in `backend/server.js`, including the SQLite
  `forge_queue.db`, `/api/forge/submit`, `/api/forge/approve/:id`,
  `/api/forge/reject/:id`, `/api/forge/task`, and Python bridge aliases.

V1 limitations to carry into the roadmap:

- Run state is JSON-file based and not transaction-safe under concurrent runs.
- Audit records are append-only JSONL, not relationally queryable.
- Staged workspace is a directory copy, not a git worktree or container.
- Verification uses command allowlists but not a container sandbox.
- Generated code is single-agent oriented with only coarse review metadata.
- Model selection is mostly provider string plus local fallback, not a tracked
  routing decision with cost and quality metrics.
- Legacy queue state and canonical run state are not yet unified.

## V2 Goal

V2 makes the V1 contract durable, concurrent, auditable, and safely isolated
without changing the UI contract more than necessary.

Primary V2 outcomes:

- Replace JSON run state with SQLite in local mode and Postgres in server mode.
- Preserve the V1 `/api/forge/runs` response shape while backing it with tables.
- Stage each run in a git worktree, with optional container execution for
  verification.
- Split generation, policy, verification, and review into named agent stages.
- Record model routing, token usage, latency, cost estimate, and quality signals
  per stage.
- Keep owner approval mandatory for writes, dependency installs, external
  delivery, payments, wallets, and live apply.

## V3 Goal

V3 turns AscendForge into a production-grade supervised build swarm.

Primary V3 outcomes:

- Container-first execution with per-run filesystem, network, CPU, memory, and
  time policies.
- Multi-agent debate and independent review before apply.
- Queue-backed orchestration for parallel runs and retries.
- Automated eval suites that compare proposed changes against historical
  baselines.
- Tenant-aware project, run, artifact, approval, and audit isolation.
- Pull request and deployment preparation as explicit, approval-gated actions.

## Storage Plan

Use the same logical schema in SQLite and Postgres. SQLite remains the local
desktop default. Postgres is enabled for multi-user and long-running server
deployments.

### Core Tables

`forge_projects`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Existing project id. |
| `tenant_id` | text not null | Defaults to `default` during migration. |
| `name` | text not null | Project display name. |
| `root_path` | text not null | Absolute local path or checked-out worktree root. |
| `target_type` | text not null | `internal_repo`, `external_project`, `scratch`, etc. |
| `package_type` | text | Node, Python, generic. |
| `write_access` | boolean not null | Existing project write flag. |
| `allowed_write_paths` | json/jsonb not null | Array of path prefixes. |
| `verification_commands` | json/jsonb not null | Allowlisted command list. |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Existing `run_id`. |
| `tenant_id` | text not null | Tenant isolation. |
| `project_id` | text not null | FK to projects. |
| `goal` | text not null | User request. |
| `status` | text not null | `awaiting_approval`, `staged`, `verified`, `applied`, etc. |
| `mode` | text not null | `supervised`, `agentic_supervised`, future modes. |
| `provider` | text | V1 provider hint. |
| `max_iterations` | integer not null | Bounded loop limit. |
| `workspace_id` | text | FK to workspace record. |
| `context_pack_id` | text | FK to context pack. |
| `plan_id` | text | FK to plan. |
| `review_status` | text | Denormalized latest review state. |
| `final_report_id` | text | FK to final report. |
| `created_by` | text | User/service id. |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_context_packs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text not null | FK to runs. |
| `goal` | text not null | Snapshot of run goal. |
| `repo_summary` | json/jsonb not null | Code index summary or degraded error. |
| `relevant_files` | json/jsonb not null | Retrieved chunks. |
| `tree_paths` | json/jsonb not null | Bounded project tree. |
| `recent_sessions` | json/jsonb not null | Recent Forge session context. |
| `constraints` | json/jsonb not null | Approval and blocked-action constraints. |
| `risk_policy` | json/jsonb not null | Policy snapshot used for the run. |
| `verification_commands` | json/jsonb not null | Commands selected for the run. |
| `generated_at` | timestamp not null |  |

`forge_plans`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Existing plan id. |
| `run_id` | text | Nullable for legacy/session plans. |
| `project_id` | text |  |
| `goal` | text not null |  |
| `state` | text not null | `planned`, `replanned`, `abandoned`. |
| `readiness` | json/jsonb not null | Node, Python, sandbox, model readiness. |
| `selected_skills` | json/jsonb not null | Skill ids and metadata. |
| `task_plan` | json/jsonb not null | Ordered stage list. |
| `impacted_files` | json/jsonb not null | Planned file scope. |
| `risk_level` | text not null | `safe`, `caution`, `dangerous`. |
| `required_approvals` | json/jsonb not null | Approval requirements. |
| `verification_commands` | json/jsonb not null |  |
| `rollback_strategy` | text not null |  |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_actions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Existing action id. |
| `run_id` | text | FK to runs. |
| `plan_id` | text | FK to plans. |
| `project_id` | text | FK to projects. |
| `type` | text not null | `write_file`, `security_scan`, `test_run`, etc. |
| `label` | text not null | UI label. |
| `description` | text |  |
| `status` | text not null | `pending_approval`, `staged`, `verified`, `applied`, etc. |
| `risk` | text not null | V1 coarse risk. |
| `risk_level` | text | Policy risk level. |
| `approval_required` | boolean not null |  |
| `approval_reason` | text |  |
| `file_path` | text | Single-file target. |
| `files` | json/jsonb | Multi-file target. |
| `proposed_content_ref` | text | Artifact pointer for large content. |
| `diff_ref` | text | Artifact pointer for diff. |
| `policy_decision` | json/jsonb not null | Policy output snapshot. |
| `expected_result` | text |  |
| `rollback_plan` | text |  |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_patches`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | New stable patch id. |
| `run_id` | text not null | FK to runs. |
| `action_id` | text not null | FK to actions. |
| `iteration` | integer | Agentic iteration. |
| `files` | json/jsonb not null | Target files. |
| `diff_ref` | text | Artifact pointer. |
| `policy` | json/jsonb not null | Policy result. |
| `status` | text not null | `pending_approval`, `staged`, `blocked`, `applied`. |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_approvals`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Single approval record. |
| `run_id` | text | FK to runs. |
| `action_id` | text | FK to actions. |
| `patch_id` | text | FK to patches. |
| `approval_type` | text not null | `stage`, `verify`, `apply`, `dependency`, `external`. |
| `decision` | text not null | `approved`, `rejected`, `expired`, `revoked`. |
| `decided_by` | text not null | User/service id. |
| `reason` | text | Operator note. |
| `policy_snapshot` | json/jsonb not null | Policy state at approval time. |
| `created_at` | timestamp not null | Request time. |
| `decided_at` | timestamp | Decision time. |

`forge_test_results`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key | Existing verify id. |
| `run_id` | text not null | FK to runs. |
| `workspace_id` | text | FK to workspace. |
| `iteration` | integer | Nullable for non-agentic verify. |
| `all_passed` | boolean not null |  |
| `commands` | json/jsonb not null | Commands requested. |
| `results` | json/jsonb not null | Per-command result. |
| `duration_ms` | integer | Total runtime. |
| `verified_by` | text | User/service id. |
| `verified_at` | timestamp not null |  |

`forge_reviews`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text not null | FK to runs. |
| `stage` | text not null | `policy`, `static_review`, `security_review`, `final_review`. |
| `reviewer` | text not null | Agent or human id. |
| `status` | text not null | `passed`, `warning`, `failed`, `blocked`. |
| `summary` | text not null | Human-readable result. |
| `findings` | json/jsonb not null | Structured issues. |
| `created_at` | timestamp not null |  |

`forge_final_reports`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text not null | FK to runs. |
| `status` | text not null | `applied`, `verified_not_applied`, `failed_not_applied`. |
| `summary` | text not null |  |
| `applied_files` | json/jsonb not null |  |
| `snapshots` | json/jsonb not null |  |
| `test_result_id` | text | FK to latest test result. |
| `next_steps` | json/jsonb not null |  |
| `created_by` | text not null |  |
| `created_at` | timestamp not null |  |

### Execution And Artifact Tables

`forge_workspaces`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text not null | FK to runs. |
| `type` | text not null | `copy`, `git_worktree`, `container`. |
| `source_root` | text not null | Original project root. |
| `workspace_root` | text not null | Worktree or mounted path. |
| `git_base_ref` | text | Base commit/ref. |
| `git_branch` | text | Per-run branch. |
| `container_id` | text | If container-backed. |
| `copied_files` | integer | For V1 compatibility. |
| `copied_bytes` | integer | For V1 compatibility. |
| `policy` | json/jsonb not null | Network, FS, CPU, memory, timeout policy. |
| `status` | text not null | `created`, `active`, `cleaned`, `failed`. |
| `created_at` | timestamp not null |  |
| `updated_at` | timestamp not null |  |

`forge_artifacts`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text | FK to runs. |
| `kind` | text not null | `content`, `diff`, `log`, `screenshot`, `report`. |
| `path` | text not null | Local artifact path or object key. |
| `sha256` | text not null | Integrity check. |
| `bytes` | integer not null |  |
| `metadata` | json/jsonb not null | Includes mime type and retention class. |
| `created_at` | timestamp not null |  |

`forge_model_calls`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text | FK to runs. |
| `stage_id` | text | FK to stage execution. |
| `agent_id` | text not null | `planner`, `builder`, `reviewer`, etc. |
| `provider` | text not null | `ollama`, `anthropic`, `openai`, `nvidia_nim`, etc. |
| `model` | text not null | Exact model name. |
| `architecture` | text | LLM, SLM, MoE, VLM, etc. |
| `routing_reason` | text not null | Why selected. |
| `prompt_tokens` | integer |  |
| `completion_tokens` | integer |  |
| `latency_ms` | integer |  |
| `estimated_cost_usd` | numeric |  |
| `quality_score` | numeric | Evaluator output. |
| `privacy_mode` | text not null | OFFLINE, HYBRID, CONNECTED. |
| `created_at` | timestamp not null |  |

`forge_stage_executions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `run_id` | text not null | FK to runs. |
| `stage` | text not null | See multi-agent stages below. |
| `agent_id` | text not null | Responsible agent. |
| `status` | text not null | `queued`, `running`, `passed`, `failed`, `blocked`. |
| `input_ref` | text | Artifact or JSON pointer. |
| `output_ref` | text | Artifact or JSON pointer. |
| `metrics` | json/jsonb not null | Stage-specific metrics. |
| `started_at` | timestamp |  |
| `finished_at` | timestamp |  |

`forge_audit_events`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text primary key |  |
| `tenant_id` | text not null |  |
| `run_id` | text |  |
| `actor` | text not null | User, service, or agent id. |
| `event` | text not null | `forge_run_created`, `forge_run_applied`, etc. |
| `risk_level` | text |  |
| `details` | json/jsonb not null | Event payload. |
| `hash` | text not null | Hash-chain entry. |
| `prev_hash` | text | Previous hash. |
| `created_at` | timestamp not null |  |

Indexes:

- `(tenant_id, project_id, created_at desc)` on `forge_runs`.
- `(run_id, stage, created_at desc)` on `forge_stage_executions`.
- `(run_id, status)` on `forge_actions` and `forge_patches`.
- `(run_id, all_passed, verified_at desc)` on `forge_test_results`.
- `(tenant_id, event, created_at desc)` on `forge_audit_events`.
- Postgres only: GIN indexes on `policy_decision`, `findings`, and
  `repo_summary` when query patterns justify them.

## Workspace And Isolation Plan

### V2 Worktree Workspace

Replace the V1 copied workspace with a per-run git worktree when the project
root is inside a git repo.

Flow:

1. Resolve project root and current `HEAD`.
2. Create branch `forge/run-{run_id}`.
3. Create worktree under `state/forge/worktrees/{run_id}`.
4. Stage generated file content in the worktree.
5. Run verification in the worktree.
6. On apply, create a commit in the worktree, then either:
   - merge/cherry-pick into the project branch after owner approval, or
   - copy files back for non-git projects using the V1 fallback.
7. Store base ref, branch, commit ids, and worktree path in
   `forge_workspaces`.

Fallbacks:

- Non-git project: keep V1 copy workspace, but track it through
  `forge_workspaces`.
- Very large repo: sparse worktree limited to context-pack files plus required
  dependency files.
- Dirty source tree: allow staging only if the dirty files are outside the
  impacted write set, otherwise require human decision.

### V3 Container Workspace

V3 wraps the worktree in a container execution profile.

Default policy:

- Filesystem: worktree mounted read-write, source repo read-only, state and
  secrets not mounted.
- Network: disabled by default.
- CPU/memory: bounded per run.
- Time: per-command and per-stage timeout.
- Secrets: denied unless an approval grants a named secret broker lease.
- Dependency install: blocked unless a dependency approval is recorded.

Container profiles:

- `forge-readonly`: analysis and static review only.
- `forge-build`: build/test/lint with no network.
- `forge-dependency`: temporary network access for approved installs only.
- `forge-browser`: UI tests with Playwright/browser access, no external
  account access without separate approval.

## Multi-Agent Stage Plan

V2 starts with deterministic stages and one responsible agent per stage. V3 adds
parallel reviewers and debate.

### V2 Stages

1. `intake`
   - Normalizes goal, project, tenant, mode, approvals needed, and risk hints.
   - Output: run record and initial stage execution.

2. `context_pack`
   - Builds project tree, code-index summary, retrieved code snippets, recent
     sessions, constraints, and verification commands.
   - Output: immutable context pack snapshot.

3. `planner`
   - Uses AscendForge skill recommendation and project metadata to create a
     task plan.
   - Output: plan, impacted files, required approvals.

4. `builder`
   - Generates proposed patches only.
   - Output: actions, patches, diff artifacts, proposed content artifacts.

5. `policy`
   - Applies path, secret, protected-module, dangerous-code, line-count,
     dependency, external-call, and destructive-action rules.
   - Output: policy decisions and blocked/warn/allowed status.

6. `stage`
   - Writes allowed patches into worktree/copy workspace after owner approval.
   - Output: staged files and workspace state.

7. `verify`
   - Runs allowlisted commands in isolated workspace.
   - Output: test results, logs, duration, command status.

8. `review`
   - Reviews the diff and verification output for correctness, risk, and scope.
   - Output: review findings and apply recommendation.

9. `apply`
   - Requires owner approval, passing verification, and no blocking findings.
   - Output: merge/copy result, snapshots, final report.

10. `memory_writeback`
    - Writes a compact summary to memory/code history after completion.
    - Output: memory/artifact references.

### V3 Agents

- `Forge Planner`: architecture-aware plan and file scope.
- `Forge Builder`: patch generation only.
- `Policy Sentinel`: security, permission, and approval enforcement.
- `Test Runner`: reproducible verification and failure triage.
- `Code Reviewer`: correctness, maintainability, and regression review.
- `Security Reviewer`: injection, secrets, external IO, and dependency review.
- `UX Reviewer`: screenshot and UI behavior review for frontend changes.
- `Release Captain`: final report, PR/deployment prep, and rollback plan.

V3 review rule:

- Apply is blocked if Policy Sentinel blocks.
- Apply is blocked if tests fail.
- Apply is blocked if Security Reviewer finds high risk.
- Apply requires at least one non-builder reviewer approval.
- Frontend UI changes require a screenshot or Playwright artifact when the
  project has a browser test profile.

## Model Routing Plan

V1 accepts a provider hint and falls back from Python chat to local Ollama
`qwen2.5-coder:14b` or configured `FORGE_OLLAMA_MODEL`.

V2 routing contract:

- Every model call records `provider`, `model`, `architecture`,
  `routing_reason`, `privacy_mode`, latency, token counts, estimated cost, and
  quality score in `forge_model_calls`.
- Routing honors `PRIVACY_MODE`:
  - `OFFLINE`: local providers only.
  - `HYBRID`: local first, external only when policy and task difficulty allow.
  - `CONNECTED`: external allowed with telemetry rules still excluding content.
- Routing honors active provider inheritance only when explicitly configured.
- External model use for code generation is allowed only if the project policy
  allows source snippets to leave the machine.

Suggested V2 model tiers:

| Stage | Default | Escalation |
| --- | --- | --- |
| Intake | SLM/local | None unless malformed goal. |
| Context pack | Embedding/vector retrieval | No generative model required. |
| Planner | Local LLM or MoE | External reasoning model for large refactors. |
| Builder | Local coder model | External coder model when local fails eval. |
| Policy | Deterministic rules | LLM only for explanation, never authority. |
| Verify | No model | LLM only for failure summarization. |
| Review | Local LLM | External reviewer for high complexity after approval. |
| Final report | SLM/local | None. |

V3 routing additions:

- Shadow routing for selected runs: compare local and external proposals without
  applying shadow output.
- Per-agent model budgets.
- Automatic downgrade after low-value model calls.
- Automatic escalation after repeated verification failures, with approval if
  external source exposure is required.
- Quality memory: store which model performed best by project type, file type,
  complexity, and verification outcome.

## Evaluation Metrics

Record metrics at run, stage, model-call, and patch level.

Run metrics:

- `run_success_rate`: applied or verified without force.
- `verification_pass_rate`: latest verify passed.
- `first_pass_rate`: verification passed on first attempt.
- `rollback_rate`: applied runs needing rollback.
- `blocked_patch_rate`: patches blocked by policy.
- `approval_latency_ms`: request to approval decision.
- `time_to_verified_ms`: run created to verified.
- `time_to_applied_ms`: run created to applied.

Patch metrics:

- Files touched.
- Lines added/removed.
- Policy violations by rule.
- Diff size.
- Scope drift: generated files outside planned impacted files.
- Test failure count after patch.

Model metrics:

- Latency per stage.
- Token counts.
- Estimated cost.
- Local vs external ratio.
- Model failure rate.
- Verification pass rate by model and stage.
- Reviewer disagreement rate.

Quality metrics:

- Static review findings per KLOC changed.
- Security findings by severity.
- User rejection rate.
- Post-apply issue rate.
- Rework rate: follow-up Forge runs touching same files within 7 days.
- Eval score from fixture tasks.

V2 minimum eval set:

- Golden small docs change.
- Golden frontend component change.
- Golden backend route change.
- Policy-blocked secret path.
- Policy-blocked path escape.
- Policy-blocked dangerous code pattern.
- Verification failure and recovery.
- Approval required before stage, verify, and apply.

V3 eval set:

- Multi-file refactor with tests.
- Frontend visual change requiring screenshot.
- Dependency install request requiring approval.
- External delivery request blocked without approval.
- Dirty worktree conflict.
- Concurrent runs against same project.
- Tenant isolation test.
- Model routing privacy-mode test.

## Migration Steps

### Phase 0: Freeze The Contract

- Document the V1 `/api/forge/runs` shape as the compatibility contract.
- Add fixture examples for run created, staged, verified, failed, applied, and
  blocked states.
- Decide which legacy `/api/forge/*` aliases remain supported.

Acceptance:

- Existing AscendForge UI can render V1 and V2 run payloads.
- No endpoint loses owner approval requirements.

### Phase 1: Add Storage Adapter

- Introduce a `ForgeStore` abstraction with JSON implementation first.
- Move V1 load/save operations behind the adapter.
- Keep endpoint responses byte-for-byte compatible where practical.

Acceptance:

- No behavior change for `/api/forge/runs`.
- Existing JSON files remain readable.
- Documentation and tests identify JSON as the legacy local store.

### Phase 2: SQLite Schema And Backfill

- Create SQLite tables matching the logical schema.
- Backfill from `projects.json`, `sessions.json`, `plans.json`,
  `actions.json`, `runs.json`, and `audit.jsonl`.
- Keep dual-read with SQLite preferred and JSON fallback.
- Store large proposed content and diffs as artifacts, not inline rows.

Acceptance:

- Restart does not lose run, approval, test result, or final report history.
- Concurrent run creation does not corrupt state.
- Backfill is idempotent.

### Phase 3: Worktree Workspace

- Use git worktree for git-backed projects.
- Preserve V1 copy workspace as fallback.
- Record workspace lifecycle in `forge_workspaces`.
- Store base ref and staged branch/commit metadata.

Acceptance:

- Verification runs in worktree, not live project root.
- Apply can be audited back to a worktree branch/commit or copied fallback.
- Dirty source tree conflicts are detected before apply.

### Phase 4: Stage Executions And Model Calls

- Persist one `forge_stage_executions` row per stage.
- Persist model routing and cost/latency data per model call.
- Show stage state in the existing run timeline without changing user flow.

Acceptance:

- Every run has at least `context_pack`, `planner`, `builder`, `policy`,
  `stage`, `verify`, and `apply` stage records as applicable.
- Every generative model call has a model-call record.

### Phase 5: Postgres Mode

- Add Postgres migrations equivalent to SQLite schema.
- Select store through configuration.
- Enforce tenant id in every query.

Acceptance:

- Same API contract passes on SQLite and Postgres.
- Tenant A cannot read tenant B projects, runs, approvals, artifacts, or audit.

### Phase 6: Container Verification

- Add container profiles for verify commands.
- Default network off.
- Require approval for dependency/network profiles.

Acceptance:

- Build/test/lint commands pass in container for supported project types.
- Network-dependent commands are blocked unless a dependency approval exists.
- Secrets are not mounted by default.

### Phase 7: V3 Multi-Agent Review

- Add reviewer agents as explicit stage executions.
- Require non-builder review before apply.
- Add security and UI review gates for relevant change types.

Acceptance:

- Apply is blocked by failed tests, policy block, high security finding, or
  missing required reviewer approval.
- Frontend changes produce review artifacts when a UI profile exists.

## Acceptance Criteria

### V2 Acceptance

- `/api/forge/runs` still returns `context_pack`, `plan`, `actions`,
  `patches`, `approvals`, `test_results`, `review`, `final_report`,
  `workspace_path`, and status fields expected by the current UI.
- Run state is durable in SQLite with idempotent JSON backfill.
- Owner approval is required before staging writes, verifying staged changes,
  and applying to live project.
- Verification executes outside the live project root.
- Blocked policy rules cannot be bypassed by apply.
- Audit events exist for run creation, approval, verification, apply, reject,
  rollback, and workspace cleanup.
- Model routing decisions are stored for every generative stage.
- The V1 copied workspace path remains available as fallback.

### V3 Acceptance

- Postgres-backed multi-tenant mode passes the same run lifecycle tests.
- Container sandbox is the default for verification in server mode.
- Network and dependency access require explicit approval.
- Multi-agent review gates are enforced before apply.
- Every final report links to artifacts, test result, approvals, and audit
  events.
- Eval dashboard can show pass rate, first-pass rate, rollback rate, approval
  latency, model cost, and policy blocks.
- Concurrent runs against one project cannot silently overwrite each other.

## Non-Goals

- Do not replace the current dashboard contract in V2.
- Do not make Money Mode a separate app.
- Do not permit autonomous publishing, external delivery, payments, wallet use,
  or dependency installs without explicit approval.
- Do not make LLM output authoritative for policy decisions.
- Do not remove legacy endpoints until the UI and tests have moved to canonical
  run APIs.

## First Implementation Slice

The safest first code slice after this documentation is:

1. Add `ForgeStore` with the existing JSON implementation.
2. Add fixtures for V1 run payload states.
3. Add SQLite migrations and a read-only backfill command.
4. Switch `/api/forge/runs` reads to store abstraction while keeping JSON writes.
5. Enable dual-write to SQLite.
6. Switch reads to SQLite after verification.

This keeps the existing V1 run flow intact while creating a clear path to
transactional storage and isolated workspaces.

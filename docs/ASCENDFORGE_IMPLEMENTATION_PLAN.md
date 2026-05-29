# AscendForge — Production Agentic Vibe-Coding Platform
## Complete Implementation Plan: Current State → V1 → V2 → V3

**Status:** V1 shipped. V2 storage adapter started (`forge_store.js` + SQLite schema). V3 designed.  
**Last updated:** 2026-05-27  
**Working branch:** `wavefield-routing`

---

## 1. Current Repo Findings

### What exists and is real (🟢)

**Node.js backend — `backend/routes/forge.js` (1984 lines)**
- `POST /api/forge/runs` — goal → context pack → LLM → extract code blocks → policy check → stage → JSON persist
- `POST /api/forge/runs/:id/approve` — owner-approval-gated staging to worktree/copy workspace
- `POST /api/forge/runs/:id/verify` — allowlist-gated command execution in staged workspace
- `POST /api/forge/runs/:id/apply` — snapshot + copy verified staged files to project root
- `POST /api/forge/agentic-run` — bounded generate→verify loop (max 5 iters), all staged, apply still needs approval
- `POST /api/forge/sessions`, `POST /api/forge/sessions/:id/messages`, `POST /api/forge/sessions/:id/messages/stream`
- `GET/POST /api/forge/projects`, `GET /api/forge/files/tree`, `GET /api/forge/files/read`, `POST /api/forge/files/write`
- `POST /api/forge/plan`, `GET /api/forge/plans`, `GET /api/forge/actions`
- `POST /api/forge/agents/blueprint`, `GET /api/forge/agents/blueprints`, `POST /api/forge/agents/:id/register`
- `POST /api/forge/sandbox`, `POST /api/forge/verify`, `POST /api/forge/rollback`
- `GET /api/forge/snapshots`, `GET /api/forge/queue`, `POST /api/forge/index`, `POST /api/forge/context`
- `GET /api/forge/summary/:projectId`, `GET /api/forge/status`, `GET /api/forge/engine/status`

**Safety systems (🟢 real)**
- `PROTECTED_PATH_PATTERNS` — blocks auth, launcher, forge controller, policy configs, start/stop scripts
- `SECRET_PATH_PATTERNS` — blocks .env, .ssh, .aws, .pem, .key, credential paths
- `BLOCKED_CODE_PATTERNS` — blocks eval, exec, subprocess, os.system, rmSync, fetch to external URLs in staged content
- `VERIFY_ALLOW` allowlist — only approved build/test/lint/typecheck commands can run
- `requireOwnerApproval()` — JWT `is_owner` claim check, blocks all write/danger operations without it
- `resolveInsideProject()` / `resolveInsideWorkspace()` — path traversal prevention
- `canWritePath()` — enforces project `allowed_write_paths` prefix list
- `isProtectedPath()` — double-check on protected modules
- `validateRunActionPolicy()` — policy engine that checks all rules and returns violation list
- `MAX_STAGED_COPY_FILES = 2500`, `MAX_STAGED_COPY_BYTES = 50MB` — workspace size caps
- Snapshots before every apply (`project/.forge_snapshots/`)
- Auto-rollback workspace on agentic-run failure

**Python layer (🟢 real, partially integrated)**
- `runtime/core/forge_controller.py` (648 lines) — `ForgeController.submit_change()`, `approve()`, `reject()`, `rollback()`, `profit_impact_analysis()`, `roi_suggestions()`
- `runtime/runtime/sandbox_executor.py` (350 lines) — AST security scan + restricted exec namespace, disallows subprocess/ctypes/socket
- `runtime/agents/ascend-forge/ascend_forge.py` (2037 lines) — patch lifecycle, scan_system(), approve_patch(), web_research(), schedules, slash commands
- `runtime/agents/ascend-forge/ui-engine/` — component scanner, style analyzer, vision runner, optimizer, patch generator, async multi-component loop

**Frontend (🟢 real UI, 🟡 some disconnected buttons)**
- `frontend/src/components/pages/AscendForgePage.jsx` (360 lines) — 3-pane layout, session/run/action state
- `frontend/src/components/pages/forge/panels.jsx` (961 lines) — ProjectPicker, FileTree, ChatPane, DiffViewer, ActionQueue, Terminal, PolicyPreview, ForgeSystemPanel, AgentBlueprintPanel, FileEditor, UnderstandPane, AgenticPane, RunTimeline
- `frontend/src/components/forge/ForgeQueuePanel.jsx` — queue panel component

**Storage (🟡 V1 JSON, V2 started)**
- `backend/services/forge_store.js` (295 lines) — ForgeStore with SQLite (`better-sqlite3`) + JSON fallback, `forge_runs`/`forge_run_actions`/`forge_run_audit` tables
- JSON state files: `forge/projects.json`, `forge/sessions.json`, `forge/plans.json`, `forge/actions.json`, `forge/runs.json`, `forge/audit.jsonl`

### What is real but not wired (🟡)

| Item | Status | Gap |
|------|--------|-----|
| `runtime/core/code_indexer.py` | Exists | Not verified as called from forge routes at `/api/forge/index` |
| Python ForgeController `submit_change()` | Exists | Called via `run_forge.py` spawn; spawn path not fully tested |
| `sandbox_executor.py` | Exists | Only called for `security_scan` action type, not for staged code validation |
| UI-engine auto_loop | Exists | Has CLI; not called from any HTTP route |
| `AgentBlueprintPanel` / `ForgeSystemPanel` | Rendered | Blueprint create/register calls are wired; skills page is read-only |
| `UnderstandPane` / `AgenticPane` | Rendered | UI exists, agentic-run API call needs verification |

### Safety risks identified (🔴)

| Risk | Location | Severity |
|------|----------|----------|
| `exec()` called with shell commands for verify | `forge.js:1742,1768` | MEDIUM — mitigated by `isVerifyAllowed` allowlist |
| `spawn()` Python subprocess with user-supplied `goal` passed to prompt | `forge.js: runForgePython()` | LOW — goal is not shell-executed, only sent as JSON stdin |
| `_execute_real_patch()` writes files based on diff preview | `ascend_forge.py:1164` | MEDIUM — diff applied to real files without workspace isolation |
| `scan_system()` calls `subprocess.run(['ai-employee', 'doctor'])` | `ascend_forge.py:830` | LOW — binary path hardcoded, timeout=30 |
| ForgeStore JSON mirror writes on every run | `forge_store.js` | LOW — concurrent runs can corrupt JSON under high load |
| No container sandbox for verify commands | `forge.js:1740-1768` | HIGH — commands run in live project root or copy, not container |
| No rate limit on `/api/forge/runs` | `forge.js` | MEDIUM — each run spawns LLM call, could exhaust budget |
| Legacy `/api/forge/submit` still active | `server.js` | LOW — old endpoint without full V1 policy |

---

## 2. Target AscendForge Architecture

```
User Input (Chat + Goal)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│              AscendForge Orchestrator (Node.js)          │
│   intake → context_pack → planner → builder → policy    │
│   → approval gate → stage → verify → review → apply     │
│   → memory_writeback                                     │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼──────────────────────────┐
    ▼          ▼                          ▼
┌────────┐ ┌──────────────────┐  ┌───────────────────┐
│ Forge  │ │  Workspace Layer  │  │  Eval & Metrics   │
│ Store  │ │  (worktree/copy/  │  │  Dashboard        │
│(SQLite)│ │   container)     │  │                   │
└────────┘ └──────────────────┘  └───────────────────┘
               │
    ┌──────────┼────────────────┐
    ▼          ▼                ▼
┌────────┐ ┌──────────┐  ┌──────────────┐
│Python  │ │ Sandbox  │  │ Code Indexer │
│Agents  │ │Executor  │  │ (per-project)│
│(LLM)   │ │(container│  │              │
└────────┘ └──────────┘  └──────────────┘
```

### Layer responsibilities

| Layer | Responsibility | Tech |
|-------|----------------|------|
| **Orchestrator** | Run lifecycle, stage sequencing, approval gating | Node.js Express |
| **Context Engine** | Code index, tree, RAG retrieval, session history | Python code_indexer + vector store |
| **Planner Agent** | Goal → task plan → impacted files → skills → risk | LLM (local first) |
| **Builder Agent** | Patch generation from goal + context | Local coder LLM |
| **Policy Sentinel** | Path/secret/pattern/scope/size policy checks | Deterministic rules + AST scan |
| **Workspace Layer** | Isolated file staging (worktree/copy/container) | git worktree + optional Docker |
| **Verify Engine** | Allowlisted build/test/lint in isolated workspace | child_process + container |
| **Review Agents** | Code review, security review, UX review | LLM reviewers |
| **Forge Store** | Durable run/action/patch/approval/audit state | SQLite (V2) → Postgres (V3) |
| **Eval Center** | Run metrics, model metrics, quality scores | Aggregate queries on forge_store |
| **UI Command Center** | 3-pane: chat + tree | diff viewer | action queue + terminal | React |

---

## 3. Gap Analysis Against Target

| Target Component | V1 Status | V2 Gap | V3 Gap |
|-----------------|-----------|--------|--------|
| Agent Orchestrator | 🟢 Node routes | Stage execution records | Queue-backed parallel runs |
| Repo Intelligence | 🟡 code_indexer exists, not verified active | Wire + test index route | Per-project incremental index |
| Context Engine | 🟢 buildContextPack() works | Persist context pack as artifact | Semantic RAG per project type |
| Tool Registry / MCP | 🟡 ToolRegistry exists in Python | Expose to forge agents | Full MCP protocol |
| Sandboxed Execution | 🔴 allowlist only, no container | Git worktree (started) | Container with network policy |
| Permission System | 🟢 requireOwnerApproval + policy | Approval records in DB | Tenant RBAC + approval expiry |
| Memory System | 🟡 Python memory_router | memory_writeback stage | Per-project code history |
| Skills Library | 🟢 AscendForgeEngine.listSkills() | Skill usage metrics | Skill performance tracking |
| Planner Agent | 🟡 createPlan() static rules | LLM-backed task breakdown | Architecture-aware planner |
| Builder Agent | 🟢 LLM → extractCodeActions() | Stage execution record | Multiple builder attempts |
| Reviewer Agents | 🔴 No dedicated reviewer | Code review stage | Multi-agent debate |
| Test/Verify | 🟢 allowlist exec in workspace | Container isolation | Parallel test workers |
| Diff Review UI | 🟢 DiffViewer panel | Side-by-side enhanced | Inline comment threads |
| Build Console | 🟢 Terminal component | Stream output via SSE | Container log streaming |
| Safety Center | 🟡 policy rules + BLOCKED_CODE | Policy violation dashboard | LLM-never-authoritative rule |
| Eval Center | 🔴 No eval dashboard | Run metric queries | Golden fixture eval suite |
| Forge Store | 🟡 JSON + SQLite started | Full SQLite schema | Postgres mode |

---

## 4. Implementation Phases

### Phase 0 — Contract Freeze + Tests (NOW, ~2 hrs)
**Goal:** Lock V1 contract so nothing can accidentally break it.

- [ ] Add fixture JSON files for all V1 run states: `created`, `staged`, `verified`, `applied`, `verify_failed`, `blocked`
- [ ] Write `tests/test_forge_run_routes.js` (already exists per V2 plan — verify it actually passes)
- [ ] Document which legacy `/api/forge/submit` aliases must stay
- [ ] Add rate limit to `/api/forge/runs` (10/min per user, 60/min global)

**Definition of done:** `npm test` includes forge route tests, all pass, no legacy endpoints removed.

---

### Phase 1 — ForgeStore Full SQLite Schema (3-4 hrs)
**Goal:** All run state durable in SQLite. JSON stays as read fallback.

**Files to create/modify:**
- `backend/services/forge_store.js` — add all tables from schema plan (already has 3 tables, need 12 more)
- `backend/migrations/forge_v2_schema.sql` — idempotent migration
- `backend/services/forge_store_migrate.js` — backfill from JSON → SQLite

**Tables to add:**
```sql
forge_projects, forge_context_packs, forge_plans, forge_actions (upgrade),
forge_patches, forge_approvals, forge_test_results, forge_reviews,
forge_final_reports, forge_workspaces, forge_artifacts, forge_model_calls,
forge_stage_executions, forge_audit_events
```

**API changes:** None (response shape preserved). Internal reads switch to SQLite with JSON fallback.

**Definition of done:**
- Restart does not lose run/approval/test result history
- Concurrent `POST /api/forge/runs` does not corrupt state (SQLite WAL mode)
- Backfill from JSON is idempotent

---

### Phase 2 — Git Worktree Workspace (V2 worktree, 4-5 hrs)
**Goal:** Verification never touches live project root. All staging in git worktrees.

**Note:** `createGitWorktreeWorkspace()` and `removeRunWorkspace()` already exist in `forge.js`. This phase makes them the default, records workspace metadata in `forge_workspaces`, and adds dirty-tree detection.

**Files to modify:**
- `backend/routes/forge.js` — upgrade `ensureRunWorkspace()` to persist to `forge_workspaces` table
- `backend/services/forge_store.js` — add `upsertWorkspace()`, `getWorkspace()`

**New behavior:**
```
POST /api/forge/runs
  → detect git repo (already done)
  → create branch forge/run-{id} in worktree
  → record in forge_workspaces: type='git_worktree', git_base_ref, git_branch
  → stage files into worktree (already done)
  → verify in worktree (already done)
  → apply: merge worktree branch or copy-back (need to add merge path)
  → cleanup: git worktree remove (already done)
```

**Safety additions:**
- Block staging if source tree is dirty AND impacted files overlap dirty set
- Store `git_base_ref` so apply can detect divergence

**Definition of done:**
- Verify runs in worktree, not live project root
- `forge_workspaces` row exists for every run with workspace info
- Dirty tree detection works and returns clear error

---

### Phase 3 — Stage Execution Records + Model Call Tracking (3-4 hrs)
**Goal:** Every stage has a DB record. Every LLM call has cost/latency data.

**Files to modify:**
- `backend/routes/forge.js` — wrap each stage with `startStage()` / `completeStage()` helpers
- `backend/services/forge_store.js` — add `insertStageExecution()`, `updateStageExecution()`, `insertModelCall()`
- `backend/services/model_cost_estimator.js` (new) — token → USD estimate by provider/model

**Stage instrumentation pattern:**
```javascript
const stage = store.startStage({ run_id, stage: 'builder', agent_id: 'forge-builder' })
try {
  const result = await callPythonChat(prompt, 90000)
  store.recordModelCall({ run_id, stage_id: stage.id, provider, model, latency_ms, prompt_tokens, ... })
  store.completeStage(stage.id, { status: 'passed', output_ref: artifactId })
} catch (err) {
  store.completeStage(stage.id, { status: 'failed', metrics: { error: err.message } })
}
```

**Definition of done:**
- Every run has stage execution rows for: context_pack, planner, builder, policy, stage, verify, apply (as applicable)
- Every `callPythonChat()` has a model_call row with provider, model, latency_ms
- `/api/forge/runs/:id` response includes `stages` array

---

### Phase 4 — Code Review Agent Stage (4-5 hrs)
**Goal:** Every apply-eligible run has a code review before apply is permitted.

**Files to create:**
- `backend/forge/agents/code_reviewer.js` — calls Python LLM with diff + project context, returns findings JSON
- `runtime/forge/review_agent.py` — Python implementation if local model preferred

**Review prompt template:**
```
You are a code reviewer for project {name}.
Review this diff for: correctness, security issues, scope drift, regressions.
Output JSON: { "status": "passed|warning|failed", "findings": [...], "recommendation": "apply|review|reject" }
```

**Route changes:**
- `POST /api/forge/runs/:id/verify` → after verify passes, auto-trigger review stage
- `POST /api/forge/runs/:id/apply` → block if latest review status is `failed` or no review exists

**Definition of done:**
- Every verified run has a `forge_reviews` row before apply is permitted
- Apply is blocked if review status is `failed`
- Review findings visible in RunTimeline UI panel

---

### Phase 5 — Eval Dashboard (3-4 hrs)
**Goal:** Operators can see quality metrics. No guessing.

**Files to create:**
- `backend/routes/forge_eval.js` — eval API routes
- `frontend/src/components/pages/forge/EvalDashboard.jsx` — metrics page

**API routes:**
```
GET /api/forge/eval/summary       → run_success_rate, first_pass_rate, rollback_rate, blocked_patch_rate
GET /api/forge/eval/model-costs   → cost/latency by provider+model
GET /api/forge/eval/policy-blocks → top policy violation rules
GET /api/forge/eval/runs          → paginated run list with metrics
GET /api/forge/eval/fixtures      → golden fixture test results
POST /api/forge/eval/run-fixture  → run a single golden fixture test
```

**Definition of done:**
- Dashboard shows last-30-day: success rate, first-pass rate, avg approval latency, top blocked rules
- At least 6 golden fixture tests can be run from UI

---

### Phase 6 — Container Verification (V3, 6-8 hrs)
**Goal:** Verify commands run in container, not host process.

**Files to create:**
- `backend/forge/container/sandbox_runner.js` — Docker/Podman container lifecycle
- `backend/forge/container/profiles.js` — `forge-readonly`, `forge-build`, `forge-dependency`, `forge-browser`
- `runtime/forge/container_policy.py` — policy enforcement

**Container flow:**
```
verify request →
  pull profile (forge-build) →
  mount worktree read-write, source read-only →
  network disabled →
  run allowed commands in container →
  capture stdout/stderr as artifact →
  store result in forge_test_results →
  cleanup container
```

**Approval gates:**
- `forge-dependency` profile requires dependency approval record in `forge_approvals`
- `forge-browser` profile requires browser approval + Playwright artifact requirement

**Definition of done:**
- Default verify runs in container, not host
- Network-off enforced for `forge-build` profile
- Secrets not mounted

---

### Phase 7 — Multi-Agent Review (V3, 8-10 hrs)
**Goal:** Security reviewer + UX reviewer as independent blocking gates.

**New agents:**
- `backend/forge/agents/security_reviewer.js` — injection, secrets, external IO, dependency chain
- `backend/forge/agents/ux_reviewer.js` — screenshot diff via Playwright + vision runner
- `backend/forge/agents/release_captain.js` — final report, PR prep, rollback plan

**Review rule enforcement:**
```
Apply is BLOCKED if:
  - Policy Sentinel has violations
  - Tests failed
  - Security Reviewer finds HIGH severity
  - No non-builder reviewer has approved
Frontend changes: UX Reviewer must produce screenshot artifact
```

**Definition of done:**
- Apply blocked by security HIGH finding
- Frontend changes require UX review artifact
- Release Captain generates PR-ready summary

---

### Phase 8 — Postgres Mode (V3, 4-6 hrs)
**Goal:** Multi-user, multi-tenant deployments backed by Postgres.

**Files to create:**
- `backend/migrations/forge_v3_postgres.sql` — equivalent schema for PG
- `backend/services/forge_store_pg.js` — Postgres adapter implementing same ForgeStore interface
- `backend/services/forge_store_factory.js` — select adapter by `FORGE_DB_MODE` env

**Tenant enforcement:**
- Every query includes `WHERE tenant_id = ?`
- Tenant A cannot read tenant B runs/projects/approvals/artifacts

**Definition of done:**
- Same test suite passes on SQLite and Postgres
- Tenant isolation verified by `test_forge_tenant_isolation.js`

---

## 5. File-by-File Plan

### New files

```
backend/
  forge/
    agents/
      code_reviewer.js          # Phase 4: LLM code review stage
      security_reviewer.js      # Phase 7: security findings
      ux_reviewer.js            # Phase 7: UI/screenshot review
      release_captain.js        # Phase 7: PR prep + final report
    container/
      sandbox_runner.js         # Phase 6: container lifecycle
      profiles.js               # Phase 6: execution profiles
  migrations/
    forge_v2_schema.sql         # Phase 1: full SQLite schema
    forge_v3_postgres.sql       # Phase 8: Postgres equivalent
  services/
    forge_store_migrate.js      # Phase 1: JSON → SQLite backfill
    forge_store_pg.js           # Phase 8: Postgres adapter
    forge_store_factory.js      # Phase 8: adapter selector
    model_cost_estimator.js     # Phase 3: token → USD
  routes/
    forge_eval.js               # Phase 5: eval API

frontend/src/components/pages/forge/
  EvalDashboard.jsx             # Phase 5: metrics dashboard
  StageTimeline.jsx             # Phase 3: stage execution view
  ReviewFindings.jsx            # Phase 4: review findings panel

runtime/forge/
  review_agent.py               # Phase 4: Python code review impl
  container_policy.py           # Phase 6: container policy checker

tests/
  test_forge_run_routes.js      # Phase 0: V1 contract tests (verify existing)
  test_forge_store_sqlite.js    # Phase 1: SQLite store tests
  test_forge_worktree.js        # Phase 2: worktree workspace tests
  test_forge_stages.js          # Phase 3: stage execution tests
  test_forge_review.js          # Phase 4: review agent tests
  test_forge_eval.js            # Phase 5: eval API tests
  test_forge_tenant_isolation.js # Phase 8: tenant isolation
  fixtures/
    forge_run_created.json      # Phase 0: fixture for created state
    forge_run_staged.json       # Phase 0: fixture for staged state
    forge_run_verified.json     # Phase 0: fixture for verified state
    forge_run_applied.json      # Phase 0: fixture for applied state
    forge_run_blocked.json      # Phase 0: fixture for blocked state
```

### Modified files

```
backend/services/forge_store.js          # Phase 1: add all 14 tables
backend/routes/forge.js                  # Phase 1-4: store abstraction, stage tracking
backend/server.js                        # Phase 0: add rate limit to forge/runs
frontend/src/components/pages/forge/panels.jsx  # Phase 3-4: add StageTimeline, ReviewFindings
```

---

## 6. API / Schema Plan

### Run response shape (V1 contract — MUST NOT change)

```json
{
  "ok": true,
  "run_id": "run-abc123",
  "run": {
    "id": "run-abc123",
    "project_id": "proj-xyz",
    "goal": "Add dark mode toggle",
    "status": "verified",
    "mode": "supervised",
    "provider": "anthropic",
    "context_pack": { "relevant_files": [], "tree_paths": [], "constraints": {} },
    "plan": { "id": "plan-...", "risk_level": "caution", "task_plan": [], "impacted_files": [] },
    "actions": [{ "id": "act-...", "type": "file_update", "status": "staged", "risk": "caution" }],
    "patches": [{ "action_id": "act-...", "files": [], "status": "staged" }],
    "approvals": [],
    "test_results": [{ "id": "verify-1", "all_passed": true, "results": [] }],
    "review": { "status": "verification_passed", "summary": "..." },
    "final_report": null,
    "workspace_path": "~/.ai-employee/state/forge/runs/run-abc123/workspace"
  }
}
```

### V2 additions (additive, not breaking)

```json
{
  "run": {
    "...V1 fields...",
    "stages": [
      { "stage": "context_pack", "status": "passed", "started_at": "...", "finished_at": "..." },
      { "stage": "builder", "status": "passed", "agent_id": "forge-builder" },
      { "stage": "policy", "status": "passed" },
      { "stage": "review", "status": "warning", "findings": [{ "severity": "low", "message": "..." }] }
    ],
    "workspace": {
      "type": "git_worktree",
      "git_base_ref": "abc123def",
      "git_branch": "forge/run-abc123"
    },
    "model_calls": [
      { "stage": "builder", "provider": "ollama", "model": "qwen2.5-coder:14b", "latency_ms": 3200 }
    ]
  }
}
```

### Eval API

```
GET /api/forge/eval/summary
→ {
    "period": "30d",
    "runs_total": 142,
    "success_rate": 0.78,
    "first_pass_rate": 0.61,
    "rollback_rate": 0.04,
    "blocked_patch_rate": 0.12,
    "avg_approval_latency_ms": 45000,
    "avg_time_to_verified_ms": 12000,
    "top_policy_blocks": ["dangerous_code", "protected_path", "write_scope"],
    "cost_usd_total": 2.34
  }
```

---

## 7. UI Plan

### Current panels (🟢 keep)

| Panel | Location | Status |
|-------|----------|--------|
| ProjectPicker | Left pane top | 🟢 real |
| FileTree | Left pane | 🟢 real |
| ChatPane | Left pane main | 🟢 real |
| DiffViewer | Center pane | 🟢 real |
| FileEditor | Center pane tab | 🟢 real |
| ActionQueue | Right pane | 🟢 real |
| Terminal | Right pane | 🟢 real |
| RunTimeline | Right pane | 🟢 real |
| PolicyPreview | Overlay | 🟢 real |
| AgentBlueprintPanel | System tab | 🟢 real |

### New panels (phases)

| Panel | Phase | Purpose |
|-------|-------|---------|
| `StageTimeline` | 3 | Show stage execution progress with pass/fail per stage |
| `ReviewFindings` | 4 | Inline review findings from code/security/UX reviewers |
| `EvalDashboard` | 5 | Run metrics, model costs, policy block frequency |
| `WorkspaceInfo` | 2 | Show workspace type (worktree vs copy), git ref, branch |

### UI rules

- **Every button calls a real API or is labeled "(planned)"** — no orphan buttons
- **Terminal streams real output** — verify command stdout/stderr via SSE
- **ActionQueue shows real policy decisions** — policy block reason visible in-line
- **DiffViewer shows actual content diff** — not just metadata
- **StageTimeline auto-updates** — poll or WebSocket push from run status changes
- **Apply button disabled** unless: latest verify passed AND (if review exists) review is not `failed`

---

## 8. Agent Loop Pseudocode

### V1 (current — run in one HTTP response)

```
POST /api/forge/runs:
  context = buildContextPack(project, goal)
  plan = createPlan(engine, project, goal)
  aiText = callPythonChat(systemPrompt + context + goal)
  actions = extractCodeActions(aiText, project)[0:12]
  for action in actions:
    policy = validateRunActionPolicy(action, project)
    action.status = 'staged' if policy.allowed else 'blocked'
  run = persistRun(context, plan, actions)
  return run  # staged, awaiting approval
```

### V2 (stage-tracked, worktree)

```
POST /api/forge/runs:
  stage('intake')
    validate(goal, project, tenant)
  
  stage('context_pack')
    context = buildContextPack(project, goal)
    persistContextPack(run.id, context)
  
  stage('planner')
    plan = createPlan(engine, project, goal, context)
    persistPlan(run.id, plan)
  
  stage('builder')
    prompt = buildSystemPrompt(project, context, plan)
    aiText = callPythonChat(prompt)  → records model_call
    actions = extractCodeActions(aiText, project)[0:12]
  
  stage('policy')
    for action in actions:
      policy = validateRunActionPolicy(action, project)
      persistAction(run.id, action, policy)
  
  run.status = 'awaiting_approval'
  return run

# Human reviews ActionQueue in UI, clicks "Approve All"

POST /api/forge/runs/:id/approve:  [requireOwnerApproval]
  stage('stage')
    worktree = ensureWorktreeWorkspace(run, project)  # git worktree
    for action in approved_actions:
      stageRunAction(run, project, action, worktree)
    persistWorkspace(run.id, worktree)
  run.status = 'staged'

POST /api/forge/runs/:id/verify:  [requireOwnerApproval]
  stage('verify')
    workspace = getWorktree(run)
    results = runVerifyCommandsInWorktree(project, cmds, workspace)
    persistTestResult(run.id, results)
  
  stage('review')  # auto-triggered if verify passed
    diff = buildDiffFromStagedFiles(workspace)
    review = codeReviewer.review(diff, project, plan)
    persistReview(run.id, review)
  
  run.status = 'verified' if verify.all_passed else 'verify_failed'

POST /api/forge/runs/:id/apply:  [requireOwnerApproval]
  stage('apply')
    assert latestVerify.all_passed
    assert latestReview.status != 'failed'
    snapshots = snapshotCurrentFiles(project, actions)
    applyWorkspaceToProjRoot(workspace, project)
    persistFinalReport(run.id, applied, snapshots)
  
  stage('memory_writeback')
    memory.writeForgeRunSummary(run)
  
  cleanupWorktree(run)
  run.status = 'applied'
```

### V3 (multi-agent, container, parallel review)

```
POST /api/forge/runs:
  [intake] → [context_pack] → [planner] → [builder]
  → [policy_sentinel: blocks if violations]
  → [approve gate]
  → [stage into container workspace]
  → [verify in forge-build container]
  → parallel reviewers:
      [code_reviewer] ─────────────────────┐
      [security_reviewer (if code risk)] ──┤→ aggregate: APPROVE|WARN|BLOCK
      [ux_reviewer (if frontend change)] ──┘
  → [release_captain: generate PR + final report]
  → [apply gate: requires passing tests + non-builder approval]
  → [memory_writeback]
```

---

## 9. Safety Model

### Non-bypassable rules

| Rule | Where enforced | Bypass path |
|------|---------------|-------------|
| Owner approval for all writes | `requireOwnerApproval()` | None — JWT claim check |
| Path traversal prevention | `resolveInsideProject()` | None — resolved paths compared |
| Secret path block | `SECRET_PATH_PATTERNS` | None — regex on normalized path |
| Protected module block | `PROTECTED_PATH_PATTERNS` | None — regex on normalized path |
| Dangerous code pattern block | `BLOCKED_CODE_PATTERNS` | None — content scan |
| Verify allowlist | `isVerifyAllowed()` | None — regex against fixed list |
| Apply requires passing verify | `latestVerificationPassed()` | `force: true` (audited) |
| No autonomous outreach/payment | HITL gate + money_mode | None |

### V2 additions

- `forge_approvals` table — every approval decision is a permanent DB record
- Hash-chain audit log — `forge_audit_events` with `hash` + `prev_hash`
- Workspace isolation — apply blocked if verify was not run in same workspace
- Apply blocked if review status is `failed` (code reviewer or security reviewer)

### V3 additions

- Container isolation — no host process execution for verify
- Network-off by default — dependency installs require explicit `forge-dependency` approval
- LLM never authoritative for policy — all policy decisions are deterministic rules
- Multi-reviewer consensus required before apply

### Risk levels

```
LEVEL 0: Read-only (analysis, context pack, code review read)    → always allowed, logged
LEVEL 1: Stage to workspace (worktree write, not live)           → requires approval
LEVEL 2: Verify (run commands in isolated workspace)             → requires approval + allowlist
LEVEL 3: Apply (copy to live project root)                       → requires approval + passing verify + review
LEVEL 4: External (deploy, publish, payment, install)            → blocked by default, dual-confirm required
LEVEL 5: Protected (auth, launcher, forge controller, .env)      → always blocked
```

---

## 10. Testing / Eval Plan

### V2 minimum test suite

```
tests/
  fixtures/
    forge_run_created.json     — fresh run, no approvals
    forge_run_staged.json      — approved, staged to workspace
    forge_run_verified.json    — verify passed
    forge_run_applied.json     — applied to project
    forge_run_blocked.json     — policy blocked action
    forge_run_verify_failed.json — verify failed

  test_forge_run_routes.js     — V1 contract: create, approve, verify, apply, rollback
  test_forge_store_sqlite.js   — SQLite persistence, backfill, concurrent writes
  test_forge_worktree.js       — worktree creation, dirty-tree detection, cleanup
  test_forge_stages.js         — stage execution records, model call records
  test_forge_review.js         — code review stage, apply blocked by failed review
  test_forge_policy.js         — each BLOCKED_CODE_PATTERN, SECRET_PATH, PROTECTED_PATH
  test_forge_eval.js           — eval API metrics, golden fixture runs
```

### Golden fixture tests (Phase 5)

| Fixture | Expected result |
|---------|----------------|
| Small docs change (README.md) | Success, no policy blocks |
| Frontend component change | Success, UX review triggered (V3) |
| Backend route change | Success, code review passes |
| Secret path attempt (.env write) | BLOCKED by SECRET_PATH_PATTERNS |
| Path escape attempt (../../etc) | BLOCKED by resolveInsideProject |
| Dangerous code (subprocess.run) | BLOCKED by BLOCKED_CODE_PATTERNS |
| Protected path (start.sh) | BLOCKED by PROTECTED_PATH_PATTERNS |
| Verify failure + recovery | verify_failed → re-run → verified |
| Approval required before apply | Blocked without owner JWT claim |
| Approval required before stage | Blocked without owner JWT claim |

### Quality signals to track

- `run_success_rate` — target: >75%
- `first_pass_rate` — target: >50%
- `blocked_patch_rate` — alert if >20% (may indicate bad prompts)
- `rollback_rate` — alert if >5%
- `avg_time_to_verified_ms` — target: <30s for single-file changes
- `approval_latency_ms` — not a system metric; human-dependent

---

## 11. V2 Optimization Plan

### Speed

| Optimization | Impact |
|-------------|--------|
| Context pack runs in parallel (tree + index + RAG in Promise.all) | -40% context pack time |
| Model streaming with chunked SSE to UI | Perceived latency -60% |
| Code index pre-warmed at project open, not on first run | -2s per run |
| Diff generation server-side before LLM response | Instant diff display |
| SQLite WAL mode + connection pool | Concurrent run support |

### Safety

| Optimization | Impact |
|-------------|--------|
| Stage every action to worktree before showing in UI | No partial-apply possible |
| Hash-chain audit log | Tamper-evident trail |
| Approval record linked to specific workspace state | Prevents replay attacks |
| Auto-expire approvals (default: 30min) | Stale approvals blocked |

### Autonomy (supervised only)

| Feature | Gate |
|---------|------|
| Auto-approve LOW-risk actions (typos, docs) | Owner-configurable, off by default |
| Auto-retry verify after simple lint failures | Max 2 auto-retries, owner-configurable |
| Code review auto-pass for trivial changes (<5 lines, no logic) | Still recorded, just not blocking |

### Model routing

| Optimization | Impact |
|-------------|--------|
| Local coder model (qwen2.5-coder:14b) as default for builder | Zero API cost for small changes |
| Escalate to external only if local fails verify 2x | Controlled cost |
| Track quality by model+project_type — prefer winners | Self-improving routing |
| Privacy mode enforcement | No code leaves machine in OFFLINE mode |

### Enterprise quality

| Feature | Phase |
|---------|-------|
| Tenant-aware project/run/approval isolation | V3 (Postgres) |
| SSO/OIDC for operator identity | V3 |
| Retention policy on artifacts (30-day default) | V3 |
| PR preparation action (git branch + description) | V3 Phase 7 |
| Automated eval regression suite (run on every PR) | V3 Phase 5+ |

---

## Execution Order

```
NOW (Phase 0):  Freeze V1 contract, add rate limits, verify existing test file
WEEK 1 (Ph 1):  Full SQLite schema, backfill from JSON, dual-write
WEEK 1 (Ph 2):  Worktree as default workspace, workspace DB record
WEEK 2 (Ph 3):  Stage execution records, model call tracking, StageTimeline UI
WEEK 2 (Ph 4):  Code review agent, apply-blocking, ReviewFindings UI
WEEK 3 (Ph 5):  Eval dashboard, golden fixtures, metric queries
WEEK 4 (Ph 6):  Container verification (V3 start)
WEEK 5 (Ph 7):  Multi-agent review (V3)
WEEK 6 (Ph 8):  Postgres mode + tenant isolation (V3)
```

---

## First Code Slice (do now)

Per user V2 plan, the safest first slice is:

1. **Rate limit** `POST /api/forge/runs` — 10/min per user (add to existing rate limiter)
2. **Verify** `tests/test_forge_run_routes.js` passes (run it now)
3. **Add** `backend/migrations/forge_v2_schema.sql` — all 14 tables, idempotent
4. **Extend** `forge_store.js` to create all tables on init
5. **Add** backfill: `forge_store_migrate.js` reads JSON → upserts to SQLite
6. **Switch** `/api/forge/runs` list read to SQLite (with JSON fallback)
7. **Dual-write** new runs to SQLite + JSON

This changes zero endpoint behavior while making storage durable.

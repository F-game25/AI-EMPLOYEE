# Ascend Forge V7 Controlled Execution Implementation

## Implemented

- Added `backend/services/forge_v7_execution.js`.
  - Persists V7 state under existing Forge home.
  - Creates isolated workspaces with git worktree preferred and temp copy fallback.
  - Stores patch proposal artifacts.
  - Applies patches inside sandbox workspaces.
  - Selects and runs validation checks from changed files and available project scripts.
  - Creates apply approval records.
  - Applies to the main workspace only after Level 3 plus approved apply approval.
  - Creates rollback artifacts with reverse patch data.
  - Writes V7 report and memory lesson records.

- Added authenticated V7 Node routes.
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/propose-patch`
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/sandbox`
  - `POST /api/forge/v7/workspaces/:workspaceId/apply-patch`
  - `POST /api/forge/v7/workspaces/:workspaceId/validate`
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/request-apply`
  - `POST /api/forge/v7/approvals/:approvalId/approve`
  - `POST /api/forge/v7/approvals/:approvalId/reject`
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/apply`
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/post-validate`
  - `POST /api/forge/v7/projects/:projectId/goals/:goalId/rollback`
  - `GET /api/forge/v7/projects/:projectId/execution-state`
  - `GET /api/forge/v7/workspaces/:workspaceId`

- Added V7 websocket events.
  - `forge:v7_patch_proposed`
  - `forge:v7_sandbox_created`
  - `forge:v7_patch_applied_to_sandbox`
  - `forge:v7_sandbox_validation_started`
  - `forge:v7_sandbox_validation_completed`
  - `forge:v7_apply_approval_requested`
  - `forge:v7_apply_approved`
  - `forge:v7_apply_rejected`
  - `forge:v7_patch_applied_to_workspace`
  - `forge:v7_post_apply_validation_started`
  - `forge:v7_post_apply_validation_completed`
  - `forge:v7_rollback_available`
  - `forge:v7_rollback_applied`
  - `forge:v7_execution_blocked`

- Updated frontend.
  - Added V7 API methods under `api.forge.v7`.
  - Added `forgeStore.v7` state and handlers.
  - Added V7 Execution view to canonical `AscendForgePage.jsx`.
  - Added real controls for mode selection, proposal, sandbox creation, sandbox apply, validation, apply approval, approved apply, post-validation, and rollback.

- Preserved V6 boundaries.
  - Python direct `/api/v5/projects/*` JSON-state endpoints are disabled by default.
  - Node remains the authenticated persistence and execution boundary.
  - GitHub publish remains branch + PR only and separate from V7 apply.

## Safety Behavior

- Level 0 cannot propose or apply.
- Level 1 can create patch proposal artifacts only.
- Level 2 can create sandbox workspaces, apply patch to sandbox, validate, and request approval.
- Level 3 is required for main workspace apply and still requires an approved apply record.
- V7 does not commit or push.
- Rollback requires explicit `confirm:true`.

## Verification Completed

- `node --check backend/routes/forge.js`
- `node --check backend/services/forge_v7_execution.js`
- `node --check backend/routes/index.js`
- `python3 -m py_compile runtime/agents/problem-solver-ui/server.py`
- `npm --prefix frontend run build`

## Remaining Recommended Smoke

- Start the app locally and run a V7 proposal against a disposable test file.
- Verify Level 0, Level 1, Level 2, and Level 3 behavior through the UI.
- Confirm no commit or push occurs during V7 apply.
- Exercise rollback on the disposable file after approved apply.

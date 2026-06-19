# Ascend Forge V7 Controlled Execution Audit

## Existing Execution Path

- Node `backend/routes/forge.js` is the canonical authenticated Forge API boundary.
- V5 goal execution already calls the existing agentic run path and normal Forge approval gates.
- Forge run helpers already support staged run actions, workspaces, verification, apply, reports, audit writes, and websocket broadcasts.
- `backend/services/forge_workspace.js` already provides safe project root resolution, git worktree support for run workspaces, temp-copy fallback, and git command helpers.
- `backend/services/forge_diff.js` already provides unified diff generation.
- Python V5 endpoints are compute-only after this integration; direct Python project-state endpoints are disabled by default.

## Existing Artifact And Approval State

- V5 artifacts, goals, and quality gates are persisted through `ForgeStore`.
- Forge actions are persisted in the existing actions store and exposed through runtime snapshots.
- Existing action approval routes apply supported action types, but there was no dedicated patch-proposal to sandbox-validation to approved-apply pipeline.
- Existing GitHub publish routes are now branch + PR only and separate from execution.

## Existing Validation System

- Forge runs can verify through existing run verification routes.
- Project defaults already infer some verification commands.
- There was no per-patch validation evidence object tied to a sandbox workspace and apply approval.

## Missing V7 Pieces Before This Work

- First-class patch proposal artifact.
- Isolated V7 workspace state with `git_worktree`, `temp_copy`, and `proposal_only` modes.
- Sandbox patch apply route.
- Validation selector/runner tied to changed files.
- Apply approval request schema.
- Approved-only workspace apply route.
- Post-apply validation route.
- Rollback artifact with reverse patch.
- V7 websocket events and frontend store handlers.
- V7 execution UI panels in canonical `AscendForgePage.jsx`.

## Files Modified Or Added

- `backend/services/forge_v7_execution.js`
- `backend/routes/forge.js`
- `backend/routes/index.js`
- `frontend/src/api/client.js`
- `frontend/src/store/forgeStore.js`
- `frontend/src/components/pages/AscendForgePage.jsx`
- `runtime/agents/problem-solver-ui/server.py`
- `docs/ASCEND_FORGE_V7_CONTROLLED_EXECUTION_AUDIT.md`
- `docs/ASCEND_FORGE_V7_CONTROLLED_EXECUTION_IMPLEMENTATION.md`

## Risk Notes

- Main workspace writes must stay behind Level 3 plus approved apply approval.
- Sandbox validation can be `partially_verified` when commands are unavailable; it must not be reported as full success.
- GitHub publish remains a separate branch/PR confirmation flow and is not called by V7 apply.
- Rollback requires explicit `confirm:true`.

# Technical Debt Cleanup

This document tracks cleanup work that should stay separate from feature work.
The goal is to keep the system stable while reducing drift, generated files,
mock data, and duplicate surfaces.

## Completed In Current Cleanup Pass

- Stopped generated runtime artifacts from being tracked going forward:
  `frontend/dist/`, PID files, SQLite runtime DBs/WAL/SHM files, JSONL logs,
  telemetry output, and problem-solver UI runtime state are now ignored.
- Removed tracked generated runtime artifacts from the working tree:
  `python-backend.pid`, Python `__pycache__` bytecode, runtime SQLite DB files,
  and runtime JSONL logs.
- Migrated frontend build chunking from deprecated Vite/Rolldown options to
  `build.rolldownOptions.output.codeSplitting`.
- Hardened Python tenant JWT extraction so it verifies signatures instead of
  decoding unsigned claims.
- Made the Node security test runnable without an undeclared `tape` dependency.

## Remaining Cleanup Priorities

1. Reconcile the dirty frontend page migration.
   - Several legacy pages are deleted while replacement pages are untracked.
   - Decide which routes are canonical, then remove dead imports and route aliases.
   - Verify with `npm --prefix frontend run build` and route smoke tests.

2. Consolidate auth and tenancy surfaces.
   - Node and Python now both verify JWTs, but there are multiple token helpers.
   - Define one canonical token claim contract: `tenant_id`, `org_name`, `email`,
     `role`, `sub`, `type`, `exp`.
   - Add cross-service tests for Node-issued tokens accepted by Python endpoints.

3. Finish route ownership documentation.
   - `backend/server.js` owns main execution routes such as `/api/tasks/run`.
   - `backend/routes/tasks.js` owns dashboard queue/history routes.
   - Add a route inventory test to prevent shadowing regressions.

4. Replace placeholder dashboard data with real or explicitly labeled mock data.
   - Money Mode now labels missing data.
   - Other dashboard surfaces still include seeded/random/demo metrics.
   - Each panel should either bind to a real backend source or show `MOCK DATA`.

5. Standardize tests.
   - Python tests use pytest.
   - Node tests are plain script runners.
   - Frontend tests use Vitest.
   - Add root scripts for each supported test suite and avoid undeclared test
     dependencies.

6. Split large files by boundary, not style.
   - `runtime/agents/problem-solver-ui/server.py` and `backend/server.js` are very
     large and contain unrelated responsibilities.
   - Extract only when there is a clear boundary: auth, Money Mode, tasks,
     settings, observability, or static UI.

7. Protect approval-first Money Mode behavior.
   - Keep external publishing, paid task acceptance, wallet/payment use, and
     account modification behind explicit approval.
   - Add regression tests around `dry_run` defaults and affiliate draft review.

## Verification Baseline

Use these commands after cleanup work:

```bash
node --check backend/server.js
node --check backend/tenancy.js
python3 -m py_compile runtime/core/tenancy.py runtime/skills/catalog.py runtime/agents/problem-solver-ui/server.py
PYTHONPATH=runtime python3 -m pytest tests/test_multitenant.py tests/test_agent_controller_architecture.py tests/test_architecture_hardening.py::TestSkillMetadata tests/test_economy.py
npm run test:security:node
npm --prefix frontend run build
```

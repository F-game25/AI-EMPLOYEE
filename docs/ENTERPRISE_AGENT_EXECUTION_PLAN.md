# Enterprise Agent Execution Plan

This is the durable handoff for the work needed to make AETERNUS NEXUS an enterprise-grade offline-first desktop system. It exists so the operator can shut the PC down and resume without losing the mission state from chat.

## Active Agent

`ascend-forge` is the owner agent for this mission. It must act as system overseer, vibecoding engineer, security reviewer, and rollback planner. It coordinates with `task-orchestrator`, `blacklight-security`, `engineering-assistant`, `qa-tester`, and the memory service.

The canonical machine-readable mission lives in:

- `runtime/config/system_orchestration_manifest.json` -> `enterprise_upgrade_mission`

## Operating Rules

- Launcher owns lifecycle: first boot, local build, Node, Python, dashboard readiness, diagnostics, stop, rebuild, and update.
- Offline-first is default. External APIs, dependency downloads, model downloads, publishing, payments, wallets, and account changes require explicit policy approval.
- Critical system parts must be bundled or copied into the app runtime with clear naming, license tracking, sandboxing, and security review. They must not depend on optional external extensions.
- Every phase must leave a testable artifact: code, config, docs, or a verification result.
- Every risky code/security/data change needs a rollback note before approval.

## Phase Queue

1. `startup-readiness-stability`
   - Separate `/api/health` from `/api/readiness`.
   - Gate graph/memory/agent pages until backing services are ready.
   - Keep page/widget crashes inside the dashboard instead of failing the launcher.
   - Verification:
     - `npm --prefix frontend test -- DashboardRoutes.smoke.test.jsx ErrorBoundary.test.jsx NeuralNetworkPage.readiness.test.jsx`
     - `npm --prefix frontend run build`
     - `npm --prefix launcher run verify`

2. `offline-first-local-build`
   - Ensure packaged app contains all critical runtime resources.
   - Make first boot build local assets when policy allows.
   - Keep offline mode blocking installs/downloads by default with clear UI state.
   - Verification:
     - `python3 scripts/verify_core_dependencies.py`
     - `npm run package:enterprise:linux`

3. `agent-workflows-memory`
   - Give production agents job descriptions, workflows, hooks, model needs, and approval gates.
   - Make memory systems visible and usable from UI and model orchestration.
   - Verification:
     - `python3 scripts/verify_agent_contracts.py`
     - `python3 -m pytest tests/test_memory.py tests/test_agents.py`

4. `enterprise-security-observability`
   - Test auth, RBAC, audit logs, HITL gates, local bind policy, secret handling, and diagnostics.
   - Enforce safe handling for copied open-source components.
   - Verification:
     - `python3 -m pytest tests/test_security.py tests/test_enterprise_hardening.py`
     - `npm run lint`

## Resume Command Set

After reboot, start with:

```bash
cd /home/lf/AI-EMPLOYEE
python3 scripts/verify_agent_contracts.py
python3 scripts/verify_core_dependencies.py
npm --prefix launcher run verify
```

Then continue the first failing phase from `runtime/config/system_orchestration_manifest.json`.

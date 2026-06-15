# System Reality Audit — "looks like it works" vs. actually works

**Date:** 2026-06-15 · **Method:** code scan for fake-success / fabricated-data / fallback-as-real patterns across `runtime/`, `backend/`, `frontend/` (excl. tests, node_modules), with file:line evidence.

**Verdict:** The system has a **real execution spine** (companion brain, LLM routing, memory, real-LLM agents, real artifact pipelines, honest guards in core), but several **headline "business outcome" surfaces compute fabricated numbers or fall back to mock data without the user noticing.** It is NOT all fake — but the most impressive-looking metrics (money/leads, some dashboards, mobile) are the least real. This doc maps every gap by severity so they can be made real one by one.

---

## What is ALREADY real (don't rebuild)
- **Companion brain** (`runtime/companion/*`): voice+chat → intent → broker → capabilities → real LLM. Live-verified.
- **LLM routing** (`model_lanes.py`, `ai_router.py`): real providers (Ollama/Anthropic/OpenAI/DeepSeek), hardware-aware.
- **Agents call real LLM**: sampled agents (lead-hunter-elite, partnership-matchmaker, sales-closer-pro) call `query_ai_for_agent` — real inference (with a *simulated sample* fallback string, see G2).
- **Skills** (after 2026-06-15 fix `780b11a5`): 200 skills run real LLM by default; `skills.run` bridges them to the companion.
- **Honest guards exist**: `real_execution_engine.py` + `tool_registry.py` ("never simulated success"); `unified_pipeline.py` `_SIMULATED_OUTPUT_PATTERNS` flags placeholder task output; `workflow_formatter.py` shows real-vs-simulated counts; `data_source` labels throughout.
- **Economy ledger** (`/api/economy/ledger`): real array, state `live`/`empty` honestly.
- **Real telemetry** (after this session): GPU/CPU via nvidia-smi/psutil.

---

## CRITICAL — fabricated business outcomes shown as real

### R1. Money Mode metrics are arithmetic, not real work
`runtime/core/money_mode.py` `run_content_pipeline`/`run_lead_pipeline`/`run_opportunity_pipeline` compute **fake numbers from string lengths**:
- `scraped_records = max(len(source) * 4, 10)` (line ~140)
- `filtered_leads = scraped_records // 3` (line ~141)
- `engagement_estimate = round(10 * len(platforms) * factor)` (line ~81)

**These are exactly what the money endpoints call** — `runtime/agents/problem-solver-ui/server.py:6518/6536/6552` + `features/system_api.py:357/403/426`. So the Money Mode dashboard "leads scraped / revenue / engagement" are invented.
**The real versions exist but are NOT wired**: `money_mode.py:557+` "real artifact pipelines" (`_llm_generate`, `_save_json`, `content_log.json`) actually generate + save content.
**Fix:** point the money endpoints at the real artifact pipelines; delete/retire the arithmetic ones (or keep only as a clearly-labeled `dry_run` estimate).

---

## HIGH — mock/simulated data served when the real source is absent

### R2. Backend subsystems fall back to simulated state
`backend/subsystems/index.js`: `_simulateMemory()` / `_simulateDoctor()` set `data_source:'simulated'` when the Python backend doesn't answer (lines 151-207, 361-368). It's *labeled*, and tries `live`/`python-brain` first — but the dashboards don't surface the label prominently, so "simulated" reads as real.
**Fix:** when `data_source==='simulated'`, the UI panels must show a visible "SIMULATED / backend offline" badge (or empty state), never silent numbers.

### R3. Mobile screens are hardcoded mocks
`frontend/src/components/mobile/screens/MobileDashboard.jsx` (`MOCK_STATUS`, `MOCK_AGENTS`, `MOCK_TASKS`, `cpuHistory = Math.random()`), `MobileTasks.jsx` (`MOCK_TASKS`), `MobileAgents.jsx` (`MOCK_AGENTS`). The entire mobile UI shows fixed fake data, no API wiring.
**Fix:** wire mobile screens to the same endpoints as desktop, or gate behind an explicit "demo" flag.

### R4. Agent "simulated sample" fallbacks
`lead-hunter-elite` ("## 25 Sample Leads (Simulated)"), `partnership-matchmaker` ("## 20 Partner Candidates (Simulated)") emit canned lists when the AI router is unavailable. Looks like a real deliverable.
**Fix:** on router-unavailable, return an honest error/empty, not a fabricated list.

### R5. Neural-brain workflow simulated execution
`runtime/neural_brain/workflows/nodes.py:240`: `fallback_output = ... or f"Simulated execution of {skill_name}"` — a node can report simulated success.
**Fix:** propagate honest failure when the real LAM/skill result is missing.

---

## MEDIUM — wired-but-dead / placeholder paths

### R6. RPA `/api/rpa/*` returns 500 at the Node→Python boundary
Router now mounted + mode-gated, but `makeProxy('RPA')` doesn't forward a Python-valid token → 500. (Found during computer-use work.)
**Fix:** forward a service token (or internal-localhost trust) so RPA actually runs.

### R7. CEO/briefing simulated response
`runtime/agents/problem-solver-ui/server.py:10405`: `"[CEO simulated response] Mission acknowledged..."` — a canned reply path.
**Fix:** route through the real LLM or label clearly.

### R8. OpenClaw is a disabled reference
`runtime/vendor/manifests/openclaw.json`: `runtime_code_imported:false, state:disabled`. Not wired (expected — absorbed into engine). No action unless multi-channel gateway is wanted.

---

## FIXED THIS SESSION (evidence the spine is being made real)
- **Skill dispatch placeholder** → real LLM by default (`780b11a5`).
- **GPU/CPU telemetry** → real nvidia-smi/psutil (earlier).
- **Computer-Use mode** → real browser capability behind a toggle (earlier).
- **134 skill system_prompts** backfilled.

---

## STATUS (2026-06-15 remediation pass)
- **R1 Money Mode** — FIXED (`15ab0ab7`): real artifacts via content_publish_track / data_scrape_filter_store; projections labelled `estimates:true`.
- **R4** — FALSE ALARM: the "Sample Leads (Simulated)" text is prompt input to a real LLM, honestly labelling examples. No change.
- **R5/R7** — FIXED (`20f17e62`): neural-brain node + CEO endpoint return honest failures instead of "Simulated execution"/"[CEO simulated response]".
- **System-wide enforcement** — FIXED (`185fc2f2`): `unified_pipeline.execute_tasks` downgrades any placeholder-marked output from success→simulated.
- **R6 RPA chain** — FIXED (`88cb046b`): proxy forwards JWT; OPERATOR role defined; AGENTS_EXECUTE used; RBAC fails closed. Live: mode OFF→403, mode ON→real browser session.
- **R2 degraded badges** — ALREADY SATISFIED (verified): Doctor/Memory/NeuralNetwork/SelfImprovement/Autonomy/SystemHealth panels all render a visible "⚠ DEGRADED — simulated data" / "○ SIM" badge when `data_source==='simulated'`.
- **R3 mobile mocks** — DEFERRED to a later phase (phone app), per owner.
- **R8 OpenClaw** — no action (disabled reference, expected).

## Remediation plan (priority order)
1. **R1 Money Mode → real pipelines** (highest: it's the "does it make money" core). Wire endpoints to the artifact pipelines; retire arithmetic or mark `dry_run`.
2. **R4/R5/R7 honest failures** — replace simulated fallbacks in agents/workflows with real errors/empty states (small, high-trust).
3. **R2 visible degraded-mode badges** — every `data_source:'simulated'` panel shows it.
4. **R3 mobile wiring** — real endpoints or explicit demo flag.
5. **R6 RPA proxy auth** — make `/api/rpa/*` actually execute.
6. **System-wide sweep** — extend `unified_pipeline` `_SIMULATED_OUTPUT_PATTERNS` enforcement so any task whose output matches a placeholder pattern is marked failed, not completed (turns "fake success" into a visible failure everywhere).

**Principle (already in `tool_registry.py`/`real_execution_engine.py`, enforce everywhere):** a subsystem must return real output or an honest error/empty — never a fabricated success.

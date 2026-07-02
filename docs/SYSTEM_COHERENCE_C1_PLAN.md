# C1 — One Execution Spine: status reconciliation + remaining-work plan

**Date:** 2026-06-30 · **Author:** Pulse (for Lars) · **Status:** COMPLETE — remaining slice (R1–R4) shipped 2026-06-30, order R2→R4→R1→R3 (Lars-approved). R1 flag `TURN_RUNNER_PIPELINE_FIRST` defaults ON.
**Parent:** `docs/SYSTEM_COHERENCE_PLAN.md` §5 Phase C1 (P0: A1,A2 · P1: A3,A4). This doc supersedes the parent's C1 sketch with **ground truth from the current code** (the parent's `file:line` map was point-in-time and is now behind the implementation).

> **Headline:** C1 is **~60% already shipped** across prior merged commits. The parent plan describes "three orchestrators" as if untouched; in reality A1-Python and the A3 seam are done and the companion already delegates to the skill chain. This doc records exactly what is done (with commit evidence) and scopes **only the remaining slice**, so we don't rebuild what exists.

---

## 1. The C1 goal (unchanged)

Collapse the three parallel "intent-classify → model-select → execute" brains into **one spine**: every chat/task/companion input resolves intent once, routes through one controlled execution path (`unified_pipeline.process_user_input`), with full telemetry + `STRICT_PIPELINE` honored, and fallbacks sitting *below* the spine — never bypassing it.

---

## 2. What is ALREADY DONE (evidence-cited — verify before building on it)

| C1 item | Status | Evidence (commit · file) |
|---|---|---|
| **A1 — Python single entry** | **DONE** | `12e5fd1d feat(coherence): C1 — Python chat flows through ONE pipeline entry`. `handle_command` (`server.py:5932-5972`) now *returns* `process_user_input(...)` as the only path; the former pre-pipeline bypass (`goal_parser` + `real_execution_engine` + `_direct_conversation_reply`) was deleted and moved INSIDE the pipeline as Phase 0. `STRICT_PIPELINE` re-raises instead of silently falling back. |
| **A3 — unified intent seam (created)** | **DONE (seam exists)** | `3717a508 feat(coherence): unified intent seam`. `runtime/core/intent_service.py::IntentService.classify()` composes the 3 classifiers (TaskOrchestrator business-intent + companion conversation-mode + engine.api normalization) into one `IntentResult` with registry-backed candidate-agent scoring (**no hardcoded intent→agent table**). |
| **Companion → skill chain** | **DONE (partial A2)** | `87ba23ea feat(coherence): one skill chain — companion broker delegates to SkillCatalog`. The companion `ExecutionBroker` routes capability execution into the shared `SkillCatalog` for the delegated path. |
| **B3 — no fabricated agent activity** | **DONE** | `ff5ba02d`. Node agent completion is now driven by real `AgentController` results, not scheduler timers (`turn-runner.js:376-388` calls `orchestrator.completeTask` only on a real `/api/tasks/run` result). |
| **G5 — canonical goal identity** | **DONE** | `032c6c11 feat(coherence): GoalRegistry — one canonical goal identity across the 3 layers`. |

**Net:** the Python hot path is already single-entry; the intent seam already exists; the companion already shares the skill catalog. The remaining incoherence is concentrated in **(a) the Node `turn-runner` fallback ladder** and **(b) full adoption of the intent seam by the companion + Node**.

---

## 3. What REMAINS for C1 (ranked, evidence-cited)

### R1 — Node `turn-runner` bypasses the pipeline (P0, A1-Node) — the main remaining gap
The chat ladder in `backend/services/turn-runner.js::runTurn` (verified 2026-06-30) runs, in order:
1. memory retrieval (`collectHybridMemoryContext`, line 313) — fine, shared preflight.
2. **tasks only:** `/api/tasks/run` → `AgentController` (line 348). AgentController *is* the application orchestrator — acceptable as a spine entry, but it is a **second Python entry** parallel to `process_user_input`.
3. **chat:** `runPythonExecution(input)` (line 394) → `server.js:2272` **spawns a separate `run_execution.py` subprocess** that calls `real_execution_engine` directly. **This is a true bypass** — a one-shot process that skips the FastAPI pipeline, its telemetry, `STRICT_PIPELINE`, and is now **redundant** with pipeline Phase 0 (the engine already runs inside `process_user_input`).
4. `requestPythonChatPayload` → `/api/chat` → `post_chat` → **the pipeline** (line 415). The spine is reached only as **rung 4**.
5. Ollama direct (line 437) → 6. keyword node-fallback (line 450).

**Problem:** for chat, the controlled spine is rung 4, sitting *below* a redundant subprocess bypass (rung 3). The plan's invariant ("pipeline first, fallback after") is violated on the Node path.

**Proposed change (smallest safe):**
- For `kind === 'chat'`: make `/api/chat` (pipeline) the **first** Python rung. Remove the `runPythonExecution` subprocess rung entirely (it duplicates Phase 0 and is the only spawner of `run_execution.py` on the chat path — confirm no other consumer relies on its envelope first).
- Keep Ollama-direct + keyword node-fallback strictly **below** the pipeline as honest degraded modes (already labeled `degraded`/`fallback` — good).
- For `kind === 'task'`: keep `/api/tasks/run` (AgentController) as the spine entry, but ensure it and `process_user_input` share the same intent seam (R2) so the same sentence routes identically.
- **Audit `run_execution.py` callers before deletion:** `server.js:3476` also calls `runPythonExecution` — that path must be re-pointed at the pipeline or justified. Do not delete the function until both call sites are migrated.

**Risk:** chat-path behavior change on the hottest route. Mitigation: feature-flag the inversion (`TURN_RUNNER_PIPELINE_FIRST=1`, default off → on after verification), keep the fallback ladder intact, add a turn-level test asserting the spine is attempted first and that degraded modes only fire when the pipeline yields nothing.

**Acceptance:** a chat turn with Python up produces `source: 'python-llm'` (pipeline) with a pipeline `trace_id` in proof; the execution-engine subprocess is never spawned for chat; killing the pipeline yields `ollama` then `node-fallback`, each marked degraded.

**STATUS: DONE.** `TURN_RUNNER_PIPELINE_FIRST` **defaults ON** (Lars). For `kind==='chat'` the turn-runner now calls the pipeline first and skips the `run_execution.py` subprocess (the two rungs are order-data-driven closures); `=0` restores legacy exec-first order. The **legacy `server.js` WS ladder** (reached only on `use_turn_runner:false`) was inverted the same way under the same flag. `tests/test_turn_runner_node.js` rewritten: proves pipeline-first (`source==='python-llm'`, exec subprocess **not** called via spy), legacy order under `=0` (`source==='execution-engine'`), and approval-gate-before-execution. Node suites green (turn-runner, agent-real-completion 6/6, boot-contract 15/15). `run_execution.py` retained — still used under flag=0 and for `kind==='task'`; not deleted.

### R2 — Companion + Node don't yet source intent through the seam (P1, A3-adoption) — **STATUS: DONE (companion); Node hint deferred to R1**
`intent_service` was consumed **only** by `unified_pipeline.py:392-393`. The companion was the real divergent *answer-path* classifier — it called `companion.intent_classifier.classify()` directly (`conversation_runtime.py:130`).

**Delivered:** `ConversationRuntime` now classifies through `IntentService.classify(text, ctx, business_intent=False).to_companion_intent()` (`conversation_runtime.py`). Key design point — **perf-safe adoption:** the seam's only LLM axis is business-intent (`TaskOrchestrator.classify_intent`, a real LLM call); the companion's conversational turns don't need a business label, so a new `business_intent=False` flag skips that axis. The conversation-mode axis *is* the same companion classifier, so `mode`/`task_type`/`confidence`/`is_command`/`reason` are byte-identical to before — zero added latency on the avatar hot path, one code path. Added `IntentResult.reason` + `to_companion_intent()`. Tests: `test_intent_service.py` 12/12 (incl. opt-out-skips-LLM + parity-with-classifier); `test_conversation_runtime.py` + `test_companion_intent_context.py` 30/30.

**Node hint — deferred to R1 (not a separate answer-path classifier):** `backend/orchestrator/index.js::submitTask` runs `classifyMessage()` → a *subsystem hint* for workflow/telemetry/money-template labeling, **not** the answer (which delegates to the seam-backed Python pipeline). Truly unifying it needs either a blocking HTTP call to a new Python `/api/intent` endpoint per submit (latency) or porting registry-scoring to Node — both exceed R2's "smallest safe change". It folds naturally into R1 (chat answer path consolidates onto the pipeline); tracked there.

### R3 — Companion `ExecutionBroker` direct side effects (P0/P1, A2-residual)
`ExecutionBroker.execute()` (`execution_broker.py:159`) runs capability adapters that call subsystems directly. The **read-only** probes (system health, memory search, logs, briefing) are fine and intentionally fast/local. The concern is any **side-effecting** capability bypassing the one spine/gateway.

**STATUS: DONE (audit + lock-in, no rewrite needed).** The audit found the broker is already correctly gated: every dispatched capability passes `SafetyGate.evaluate()` and only runs when `allowed AND not requires_approval`; the registry already carries machine-readable `risk_level` + `side_effects` per capability. **No violations** — no cap is both dispatchable and approval-gated; the two high-risk side effects (`forge.apply_patch` L3, `browser.act` L3) are approval-gated AND deliberately absent from `_dispatch`; all dispatchable caps are L0/L1 with only **local** side effects.

Classification (auto-dispatchable caps, from `capability_registry`):

| Side effect | Caps (all L0/L1, gate-cleared) |
|---|---|
| **Read-only (L0)** | system.health.read, system.tasks.active, system.logs.search, system.briefing.morning, teammate.routine.status, memory.search, forge.search_code, security.score_action, research.audit_quality, context.retrieve, company.validate/refine, browser.open/snapshot/extract/close |
| **Bounded local write (L1)** | memory.write_structured, context.write, context.compress_session, teammate.routine.configure, teammate.briefing.create_task, content.produce (staged, no posting), finance.draft, forge.run_tests (local processes), research.deep.start (network read + knowledge write), browser.capture (state file) |
| **Approval-gated, NOT dispatchable (L3)** | forge.apply_patch (modifies source), browser.act (external site) |

**Delivered:** `tests/test_broker_side_effect_audit.py` (5) locks the invariants — no dispatchable cap is `requires_approval`; only L0/L1 are dispatchable; the two dangerous caps stay gated+undispatchable; side-effecting dispatchable caps are ≤ L1; and a behavioural test proving nothing executes when the gate requires approval. Migrating the L1 local-write caps onto the C2 skill chain / R-4 P0.1 gateway is future work (the gate already mediates them).

### R4 — `classify_decision` internal routing (P1, A4) — **STATUS: DONE**
Found the residual static table: `classify_decision` got the intent label from the seam but **discarded** the seam's registry-backed `candidate_agents`, then routed `intent → agent` through the hardcoded `_INTENT_AGENT_PROFILES` dict (`unified_pipeline.py:352/401/425`).

**Delivered:** `classify_decision` now captures the full `IntentResult` in one `classify()` call and selects the agent from `candidate_agents` (registry token-overlap scoring). The static dict is renamed `_INTENT_SCORE_PROFILES` and reduced to its legitimate role — per-intent `(profit, speed, complexity)` heuristics for the DecisionEngine + a **last-resort agent fallback** only when the registry yields nothing. `execution_plan` now cites the source (`via registry` / `via fallback_profile`). Tests: `test_unified_pipeline.py` registry-primary + fallback cases; full suite 109/109.

**Acceptance met:** the hot path no longer routes `intent→agent` via a static dict (registry is primary; dict is fallback-only + scoring); routing decisions cite the source in the plan string.

---

## 4. Proposed C1 execution order (one PR, gated)

1. **R2** (adopt seam in companion + turn-runner) — lowest risk, makes routing identical everywhere first.
2. **R4** (kill any residual static routing) — small, follows naturally from R2.
3. **R1** (invert Node ladder, retire `run_execution.py` chat bypass) — behind `TURN_RUNNER_PIPELINE_FIRST` flag; the substantive change.
4. **R3** (broker side-effect classification table + guard test) — audit deliverable, no behavior change.

Each lands with its acceptance test; the PR ends with the §5-parent proof format. Estimated size: **M** (most of C1 was already paid down).

---

## 5. Security impact

- **No new external surface.** All changes are internal routing. Auth, tenancy, HITL, adversarial filter, and schema validation on `post_chat` are untouched and remain *upstream* of the spine.
- **Strictly improves safety:** removing the `run_execution.py` subprocess bypass means **every** chat input passes the adversarial filter + `STRICT_PIPELINE` + telemetry it currently skips. R3 reduces uncontrolled side-effect surface.
- **Reversibility:** R1 is feature-flagged; R2/R4 are behavior-preserving; R3 is audit-only. Every step is revertible by file.
- **Fail-closed:** the fallback ladder stays; if the pipeline errors with `STRICT_PIPELINE` off, degraded modes still answer (marked degraded) — no dead chat.

---

## 6. What I will NOT do without your explicit go

- Delete `run_execution.py` or its function until **both** call sites (`turn-runner.js:394`, `server.js:3476`) are migrated and tested.
- Change `AgentController` as the task-path entry (keep it; just align its intent source).
- Touch the companion's read-only capability adapters (they're correct).
- Any C2 work (skill/tool executability) — separate phase.

## 7. Open decisions for you

1. **R1 flag default:** ship `TURN_RUNNER_PIPELINE_FIRST` defaulting **off** (opt-in, verify in your env, then flip) or **on** (inverted immediately, fallback intact)?
2. **Task-path entry:** keep two Python entries (`/api/tasks/run` for tasks, `/api/chat` for chat) sharing the seam, or fold tasks into `process_user_input` too (larger, riskier)? Recommendation: keep both, share the seam — smallest coherent change.
3. **R3 scope now:** audit-table only this phase (recommended), or also migrate side-effecting broker caps now (pulls C2 forward)?

---

*Grounded against the live tree 2026-06-30: `server.py:4799/5118/5932`, `turn-runner.js:186-454`, `server.js:2272/3476`, `conversation_runtime.py:72-175`, `execution_broker.py:114-313`, `intent_service.py:160-174`, `unified_pipeline.py:392`. Re-verify `file:line` before each edit.*

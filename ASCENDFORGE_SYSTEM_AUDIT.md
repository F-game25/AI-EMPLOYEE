# AscendForge + Skill System Quality Audit

> Audit date: 2026-06-23 · Branch: `feat/desktop-m4-m5` · Method: direct code reading + live
> verification on an isolated backend (port 8788) during this session.
> Companion doc: `ASCEND_FORGE_AI_ENGINEER_AUDIT.md` (engine-level gaps; GAP-1/2/4/5/7 now addressed).
> Honesty rule applied: "working" only where a flow actually ran; otherwise PARTIAL/UNKNOWN.

---

## 1. Executive Summary

**Is the system currently capable of high-quality coding and task output? → PARTIALLY.**

The system is a real, large, and largely-connected AI OS — not a UI shell. In this session I ran
live: the forge run pipeline (spec→plan gate + codegen), the approval→dispatcher→`run_goal` loop,
the MCP brain connector, scoped service-token auth, the prompt cache (0-token repeat), the token
budget guard, a 2-agent swarm run (confidence 0.949), and the remote-worker registry. Memory,
model routing, sandbox, and non-coding pipelines exist as real code.

**But "high-quality" output is not yet guaranteed, for three structural reasons:**
1. **Code generation is shallow.** The forge codegen turns a single LLM response into file actions
   via regex extraction (`extractCodeActions`), now optionally fanned out to a swarm. There is no
   iterative implement→test→debug loop on the *generated code itself* — the lifecycle gates the
   plan, not the diff. Tests are not auto-run before a result is declared.
2. **Skills are prompts, not workflows.** 570 skills are curated prompt templates + metadata
   (`runtime/config/skills_library.json`); only a handful are "executable" with real tool-calling
   (`runtime/skills/forge/definitions` → `_market_research`/`_content_creation`/`_doc_intelligence`).
   Depth/quality depends on the underlying model + prompt, not on coded, tested skill logic.
3. **Output quality is largely unmeasured.** There is no automated quality scoring / benchmark
   harness that gates results. "Done" is structural (actions created), not proven (tests pass).

Net: the **plumbing is real and now well-connected** (this session closed the brain↔forge↔execute
loop, token efficiency, remote workers, and swarm). The **quality layer** (verified results,
deep skills, benchmarks, auto-test-before-done) is the missing half.

---

## 2. System Map

**Repo:** Node backend (`backend/`, ~170 forge routes), Python FastAPI runtime (`runtime/`, port
18790), React/Vite cockpit (`frontend/`, 40+ pages), Ollama (11434), state in
`~/.ai-employee/state/` (JSON + SQLite `audit.db`/`forge_queue.db`).

- **Frontend:** `AscendForgePage.jsx` (calls real `/api/forge/*`), `AgentsPage`, `ModelsPage`/
  `ModelFabricPage`, `MemoryPage`, `ComputeCenterPage`, `DeepResearchPage`, `CognitionPage`,
  `DoctorPage`, `MoneyModePage`, `forge/*` panels (Chat/Learning/Phase5/Memory). `api/client.js`
  is same-origin (`window.location.origin`) → free-port safe.
- **Node backend:** `server.js` (auth `requireAuth`+`requireScope`, tenancy, dispatcher wire-up),
  `routes/forge.js` (lifecycle gate, codegen, swarm, orchestrate, usage, queue), `routes/compute.js`
  + `routes/remote-compute.js`, `compute_fabric/*`, `services/*` (forge_store, forge_context_engine,
  forge_learning, prompt_cache_manager, token_budget_manager, swarm_coordinator,
  remote_worker_registry), `forge/dispatcher.js`.
- **Python runtime:** `core/agent_controller.run_goal` (Planner→Executor→Validator),
  `core/unified_pipeline.py` (10-phase), `core/orchestrator.py` `LLMClient` →
  `llm_provider_router`/`compute_planner` (local tiers→openrouter→rent), `forge/lifecycle/*`
  (spec→plan→implement→review→test→ship), `core/code_indexer.py`, `memory/*` (router + vector +
  bm25 + vault + wikilinks), `agents/business_swarm/*` + `core/swarm_engine.py`,
  `core/money_mode.py`, `evolution/*`+`self_evolution/*`.
- **Connected (verified this session):** MCP→forge (scoped tokens), forge submit/approve→dispatcher
  →`run_goal`, lifecycle gate→codegen, cache/budget→codegen, swarm→codegen, remote registry→assign.
- **Disconnected / weak:** generated code → sandbox test gate (not auto-run); skills → deep logic;
  quality scoring → result gating; Python engine LLM path → cache/budget (Node-only so far);
  remote worker → actual remote execution agent (protocol only; gated).

---

## 3. AscendForge coding capability

| Part | Status | Evidence |
|---|---|---|
| Understand coding request | PARTIAL | lifecycle `build_spec` gates vague goals (verified: "make it better"→blocked w/ questions) |
| Inspect repo/files | PARTIAL | `buildContextPack`+`code_indexer` (needs Python up; degrades to empty on ECONNREFUSED) |
| Build plan | PARTIAL | lifecycle `planning_engine` (deterministic slices) + `createPlan` (skill-pack) |
| Choose files to edit | PARTIAL | `contextPack.relevant_files` (keyword overlap), not call-graph aware |
| Generate high-quality code | **PARTIAL/WEAK** | single LLM response → `extractCodeActions` regex; swarm optional. No iterative refinement on the diff |
| Apply diffs safely | WORKING | `executeAction` write_file snapshots to `.forge_snapshots`, path-scoped (`canWritePath`/`isProtectedPath`) |
| Avoid overwriting unrelated code | PARTIAL | per-action staging + approval; no semantic "unrelated change" guard |
| Run tests/lint/build | PARTIAL | `test_run` action + sandbox `runSandboxedVerifyCommand` (allowlisted) — exists but NOT auto-run in default flow |
| Interpret failures / debug loop | **MISSING** | no auto test→summarize→re-plan→fix loop on generated code |
| Security review | PARTIAL | `runForgePython('security_scan')` (sandbox-runs a few core files); not per-diff |
| Architecture/perf review | PARTIAL | lifecycle `review_engine` on the patch *plan* (P0 findings block), not the actual diff |
| Detect hallucinated files/fns | MISSING | no verification that referenced files/symbols exist |
| Create missing tests / docs | MISSING (auto) | possible as a skill/goal, not automatic |
| Ask approval before risk | WORKING | autonomy levels + HITL + `requireScope` + per-action `approval_required` |
| Resume after failure | PARTIAL | dispatcher retries (bounded) + `reliabilityState.forgeFrozen`; run-level resume `/runs/:id/resume` exists |
| Clean final report | PARTIAL | `final_report`/`/runs/:id/report` fields exist; quality not scored |

**Verdict:** AscendForge can *propose* code with plan/review/test *gates around it*, safely staged
behind approval — but it does not yet *iterate to a verified, tested result*. The biggest quality
lever is an **implement→sandbox-test→debug loop** on the generated diff (currently MISSING).

---

## 4. Skill system audit

- **Defined:** `runtime/config/skills_library.json` (570 skills) — each has `id, name, category,
  description, prompt_hint, tags, compatible_agents, input_format, output_format,
  quality_standards, error_handling, best_practices, execution_steps, system_prompt`.
- **Registered/loaded:** `runtime/skills/catalog.py` (`ExecutableSkillCatalog`) + `core/skill_registry.py`
  (862 lines, `decision_engine.score` profit/complexity weighting).
- **Selected:** `dispatch_for_goal(goal, ctx)` → (1) executable skill if matched, else (2) library
  skill executed via `engine.api.generate` guided by the skill's own `system_prompt`/`execution_steps`.
- **Real logic vs prompt:** **~handful executable** (`runtime/skills/forge/definitions`:
  `_market_research` calls `web_search`+`llm_infer`; `_content_creation`; `_doc_intelligence`).
  **~560 are prompt-templates** run through the LLM. So skills have schemas/quality_standards as
  *metadata advisories*, not enforced contracts.
- **Tool calls / file I/O:** only the executable few; prompt skills produce text.
- **Tested / fail-safe / logged:** dispatch "never raises" (honest no-match); no per-skill unit tests
  or output-schema validation; usage feeds distillation opportunistically, not systematically.
- **UI:** skills surface indirectly (agents/money/forge panels); no single "570 skills" browser with
  per-skill status/quality. Hidden depth: most skills are catalog entries, not runnable workflows.

**Status: PARTIAL/MOCKED-as-depth.** The catalog is broad and well-described but shallow: quality =
prompt + model. **Per-category quality (representative):** Engineering ~4/10 (prompt-only, no exec/tests),
Marketing/Content ~6/10 (LLM is genuinely good at these), Sales/CRM ~5/10, Research ~6/10
(has real web_search exec path), Security ~3/10 (advisory text, not enforced), Data/Analytics ~4/10.
**Priority fix:** promote the top ~20 high-value skills from prompt→executable with input/output
schema validation + tests + quality checklist (Section 8).

---

## 5. Model routing & context

| Check | Status | Evidence |
|---|---|---|
| Local model support | WORKING | `_callOllama`; `compute_planner` local tiers |
| Remote fallback | WORKING | `_callClaude`; `openrouter_client`; `llm_provider_router` |
| Coding/planning/fast model selection | PARTIAL | `compute_planner.assess_compute_needs` (tier by goal); `model_lanes.py` |
| Long-context handling | UNKNOWN/NEEDS TEST | no explicit chunking path verified |
| Context window configurable from UI | UNKNOWN | `ModelFabricPage` exists; binding not verified |
| Context compression | WORKING (forge) | `forge_context_engine.compressContext`; Phase-3 prompt cache |
| RAG / memory injection | PARTIAL | `code_index` context + memory_router; not always on the codegen prompt |
| Token/cost awareness | WORKING (now) | Phase-3 `token_budget_manager` (Node) + `cost_ledger.py` (Python USD) |
| VRAM awareness | PARTIAL | `compute_planner` vram estimate; Ollama config |
| Warm/evict, arbitration, regression, quality scoring | PARTIAL/MISSING | swarm arbitrates (belief prop); no regression/quality-score gate |
| Explain model choice | PARTIAL | `task:compute_plan` broadcast carries rationale |
| Weak model on hard task | RISK | no capability-vs-difficulty guard beyond tier heuristic |

**Verdict:** routing is real and multi-provider with cost-awareness; the gap is **quality/regression
scoring** and **capability-matched assignment** (don't hand a hard task to a tiny model).

---

## 6. Memory / Neural Brain

Real, layered: `memory/memory_router.py` (semantic/episodic types, TTL cache→vector promotion by
importance), `vector_store.py`, `bm25.py` (lexical), `knowledge_vault.py` + `wikilink_resolver.py`
(linked notes), `short_term_cache.py`, `verification.py`. Tenant-aware via `tenancy.py`.

- Store/retrieve/rank: WORKING (TTL + importance + bm25 + vector). Semantic linking: PARTIAL (wikilinks).
- Outdated handling: PARTIAL (TTL); poisoning guard: PARTIAL (importance threshold, no provenance trust gate on retrieval).
- Task/project memory: PARTIAL (forge distillation → memory graph at `forge.js` Phase 7 writeback).
- Distillation actually used: PARTIAL (`forge_learning.js` creates records; consumption into future prompts is weak).
- "Explain which memory was used": MISSING in output. Cross-session: WORKING (persisted). Tests: SPARSE.

**Verdict: PARTIAL** — strong storage/retrieval, weak *closed-loop* (memory rarely changes the next
forge prompt; distillation is written more than read). CLAUDE.md security rule (treat memory as
untrusted) is only partially enforced at retrieval.

---

## 7. Execution / sandbox / safety

| Check | Status | Evidence |
|---|---|---|
| File read/write scoping | WORKING | `canWritePath`/`isProtectedPath`/`resolveInsideProject`; protected-path regexes (auth/launcher/config) |
| Shell allow/block | WORKING | `infra/sandbox/executor.js` `ALLOWED_COMMANDS` allowlist; verify allowlist (build/test/lint/pytest only) |
| Approval gates / autonomy | WORKING | HITL gate, autonomy levels, `requireScope('task-emit')` on writes |
| Sandbox isolation | WORKING | Docker sandbox + process fallback, cpu/mem/timeout/net limits, SIGKILL |
| Test execution | PARTIAL | exists (`test_run`/sandbox) but not auto-gating results |
| Remote compute exec | GATED/PROTOCOL-ONLY | Phase-7 registry + `COMPUTE_FABRIC_LIVE` gate; no live provider adapter (refuses) |
| Secrets / API keys | WORKING | env/secret broker; never logged; service-token + pairing-token are HMAC, not stored raw |
| Audit trails | WORKING | `audit.db` + per-domain jsonl (forge/remote_compute/compute_fabric) |
| Rollback | WORKING | snapshots + `/rollback`; `version_control` |
| Rate limits / multi-tenant | WORKING | per-route limiters; tenancy isolation |
| Failure recovery | PARTIAL | dispatcher retries + freeze breaker; no run-level auto-debug |
| Security tests | SPARSE | some tests exist; no prompt-injection test suite for RAG/agent paths |

**Dangerous gaps:** (a) generated code can be applied after approval **without an enforced passing
test** (test gate is opt-in); (b) **prompt-injection from repo/file/RAG content** into LLM prompts
has no guard (CLAUDE.md rule #2 not enforced on the codegen/orchestrator prompts); (c) the empty
`catch {}` in the forge codegen path silently swallowed a real bug this session — broad silent
catches hide failures.

---

## 8. UI / feedback

Extensive (40+ pages) and largely wired to real `/api` (verified `AscendForgePage` → `/api/forge/*`).
Strong: forge projects/files/runs, approvals (`ApprovalInbox`), compute center, memory page, models,
deep research, doctor/diagnostics. WS `forge:*` events stream run/queue/diagnostic updates.

**Gaps / honesty issues:**
- No **skill browser** showing all 570 skills with real per-skill status/quality (hidden depth).
- **Token budget / cache usage** (new `/api/forge/usage`) and **remote workers** (`/api/remote-compute`)
  have no UI yet — backend exists, frontend doesn't surface them.
- Run **codegen mode** (single vs swarm), **lifecycle gate** result, and **open_questions** are now in
  the run object but not rendered.
- Some pages likely show optimistic/placeholder state when Python is down (NEEDS per-page test).
- Feels like *many powerful pages*, not yet *one coherent operator console* (status of model/memory/
  budget/workers/queue in one place).

---

## 9. Benchmarks — what actually ran vs. test plan

**Verified live this session (real runs, not mocks):**
- Simple/clear goal → forge run `awaiting_approval` (lifecycle `pending_gates`). Vague goal →
  `blocked` + 4 clarifying questions. ✓ (intent gating works)
- Approve a queued task → dispatcher → `POST /api/tasks/run` (`run_goal`) → status transitions +
  audit (Python down in test → graceful `failed` w/ retry). ✓ (execute loop works)
- Repeated identical goal → prompt cache hit, **0 new tokens**. Over-budget → LLM call skipped,
  degrade to plan-only. ✓ (token efficiency works)
- `use_swarm:true` → **2 agents actually ran** via swarm engine, confidence 0.949. ✓
- Remote worker register/heartbeat/trust/assign (local fallback when not LIVE). ✓
- Scoped auth matrix (read→submit 403, emit→submit 200, bad scope 400). ✓

**NOT yet benchmarked (need full stack + a scored harness) — manual test plan:**
| # | Task | Expected | Why blocked |
|---|---|---|---|
| 1 | Multi-file feature | plan→N diffs→tests pass | no auto test-gate / scoring |
| 2 | Bug fix w/ failing test | run test→see red→fix→green | no auto debug loop |
| 3 | Security vuln detect | flag injection/secret | security skill is advisory only |
| 4 | Refactor across files | consistent multi-file diff | codegen is single-response/regex |
| 5 | Long-context repo Q&A | answer from index | index quality UNKNOWN/NEEDS TEST |
| 6 | Research summary | sourced summary | `_market_research` exec exists — TEST it |
| 7 | Architecture plan | structured doc | lifecycle plan exists — score it |

**A real benchmark harness is the #1 missing measurement tool** (Section 11/12).

---

## 10. Scorecard

| Area | Status | Score | Main problem | Priority |
|---|---|---:|---|---|
| Coding quality | PARTIAL | 4 | single-shot codegen, no diff test-loop | P0 |
| Planning quality | PARTIAL | 6 | lifecycle plans the *plan*, not the diff | P1 |
| Skill execution | IMPROVED | 6 | all 371 generated skills upgraded to full production schema (input/output contracts, safety+approval gates, audit events, wired UI); batches 1–10 complete, 0 weak backfill entries left. Still prompt-grounded (no per-skill exec harness yet) | P1 |
| Agent orchestration | WORKING | 7 | run_goal + dispatcher + MCP wired | P2 |
| Model routing | WORKING | 6 | no quality/regression scoring | P1 |
| Context handling | PARTIAL | 5 | keyword relevance; not call-graph/RAG-on-prompt | P1 |
| Memory | PARTIAL | 5 | written more than read; weak closed loop | P1 |
| Sandbox/testing | PARTIAL | 6 | exists but not result-gating | P0 |
| Security | PARTIAL | 6 | no prompt-injection guard; silent catches | P0 |
| UI feedback | PARTIAL | 6 | powerful pages, not one console; new features unsurfaced | P2 |
| Autopilot | PARTIAL | 4 | `/agentic-run` exists; no verified loop | P2 |
| Error recovery | PARTIAL | 5 | retries/freeze; no auto-debug | P1 |
| Non-coding tasks | PARTIAL | 6 | money_mode real + honest; research exec exists | P2 |
| Performance | PARTIAL | 6 | cache/budget added; no perf tests | P3 |
| Extensibility | WORKING | 7 | clean service/route patterns, scoped tokens | P3 |

---

## 11. What's working / partial-fake / critical gaps

**Working (proven):** scoped-token auth; forge submit→approve→dispatcher→run_goal; MCP brain
connector (10 tools); lifecycle spec/plan gate; prompt cache + token budget; swarm routing
(2-agent run); remote worker registry; sandbox executor; snapshots/rollback; audit trails;
money_mode pipelines (with anti-fabrication honesty); memory store/retrieve.

**Partial / fake-depth:** skills (prompt templates, not workflows); codegen (single-shot+regex);
"quality" (unscored); memory closed-loop (write>read); security review (advisory); many UI pages
(real wiring but optimistic when Python down); autopilot (exists, unverified).

**Critical gaps (ranked):**
1. **No verified-result loop** — code can be approved/applied without an enforced passing test. (P0, safety+quality)
2. **No prompt-injection guard** on codegen/orchestrator/RAG prompts (CLAUDE.md rule #2). (P0, security)
3. **No quality/benchmark harness** — quality is unmeasured, so it can't improve. (P0, measurement)
4. **Skills are shallow** — depth = prompt+model, not coded+tested workflows. (P1)
5. **Broad silent `catch {}`** in core forge paths hides failures. (P1, reliability)
6. **Memory not closed-loop** — distillation written, rarely read back into prompts. (P1)

---

## 12. Root cause

Output quality is capped because the system optimizes for **breadth and connectivity** (many
agents/skills/pages, now well-wired) over **depth and verification**. Specifically: (a) the codegen
step is a single LLM call + regex, with gates around the *plan* not the *diff*; (b) there is no
**feedback loop** (test→fail→fix→retest) and no **scoring** to tell good from bad; (c) skills carry
quality *as metadata* but nothing enforces it; (d) memory/distillation is a write-mostly loop.
Fixing quality = adding the **verify→debug→score** loop and **deepening the top skills**, not adding
more features.

---

## 13. Roadmap & exact developer tasks

### Phase A — Make it truthful
- **A1 Surface real status in UI.** Add panels for `/api/forge/usage` (budget+cache),
  `/api/remote-compute/workers`, and run `codegen`/`lifecycle`/`open_questions`. Files:
  `frontend/src/components/pages/AscendForgePage.jsx`, new `UsagePanel.jsx`/`WorkersPanel.jsx`.
  Accept: pages show live data; no placeholder when Python up. Risk: low.
- **A2 Kill silent catches.** Replace empty `catch {}` in `forge.js` codegen/run paths with
  logged, audited handling. Accept: a thrown error is visible in `python-backend.log`/audit. Risk: low.

### Phase B — Make it reliable
> **Progress 2026-06-23 (B1+B2+B3+C2 SHIPPED):**
> - **B1** wired as a real gate: auto-verify on approve (FORGE_AUTO_VERIFY) + apply blocked
>   unless `all_passed` + force-bypass now logs `forge_apply_forced_unverified risk=high`.
>   Also fixed a pre-existing staging crash (`forgeWorkspace.resolveInsideWorkspace`→forgePath).
> - **B2** `POST /runs/:id/auto-debug`: bounded verify-fail→re-codegen→re-verify loop
>   (FORGE_DEBUG_MAX_ITERS), never auto-applies (iterate-then-approve). Verified live.
> - **B3** `prompt_guard.js`: untrusted repo/history/web content wrapped in unspoofable fences
>   + injection patterns neutralized, wired into all codegen/auto-debug prompts.
> - **C2** `POST /forge/research-summary`: sourced + guarded + cached + verifier-scored research
>   (first-target workflow). `npm run bench` now 4/4 PASS.
> REMAINING: deepen the top-20 skills (C2 pattern applied broadly), D1 live remote provider adapter.
> **Progress 2026-06-24 (C3 + C4 SHIPPED):**
> - **C3** `runtime/core/routing_quality.py` — difficulty estimation + capability-vs-difficulty
>   floor guard (escalate-only) + output quality scoring + redacted model→quality ledger; wired
>   into `compute_planner` + `orchestrator.LLMClient.complete`. Tests: 16 passed.
> - **C4** memory closed-loop: provenance-trust gate on BOTH retrieval surfaces. Node
>   `backend/services/memory_trust_gate.js` filters ranked memories (confidence + corroboration +
>   provenance, injection hard-zeroed, fail-closed) and `buildContextPack` now injects the gated,
>   prompt_guard-fenced memories into the supervised codegen prompts. Python
>   `runtime/core/memory_trust.py` mirrors it and is wired into `MemoryRouter.retrieve()` (over-fetch
>   → gate → top_k, fail-closed). Shared config `runtime/config/memory_trust.json`; kill-switches
>   `FORGE_MEMORY_INJECTION` / `MEMORY_TRUST_GATE`. `vector_metadata()` now persists
>   confidence/importance so the gate reads real signals. Tests: 9 (node) + 8 (py) passed;
>   memory/routing regression green (52 passed).
> **Earlier progress note (B1 core + C1):** `backend/services/result_verifier.js`
> (code→sandbox via injected runner; research/text→quality criteria with hard gates on
> non-empty + sources) and `tests/benchmarks/` + `npm run bench` (research-first). Live:
> 3/3 PASS (research_summary 0.75, lifecycle blocks-vague, lifecycle allows-clear). REMAINING
> for full B1: wire the verifier as a hard GATE on run completion (a run can't be `completed`
> without a passing verify). REMAINING C2: deepen the research skill to be executable+sourced.
- **B1 Result verifier (auto test-gate).** New `backend/services/result_verifier.js`: after codegen,
  run the project's verification command(s) in the existing sandbox; a run cannot reach `completed`
  unless tests pass (or no tests exist → `pending_gates`, never silent success). Wire into `/runs`
  apply + dispatcher. Files: `forge.js`, `infra/sandbox/executor.js`. Accept: failing test blocks
  completion; `run.test_results.all_passed` gates status. Tests: unit + a red→green fixture. Risk: med.
- **B2 Debug loop.** On test failure, compress failure (reuse `/runs/:id/failures`) → re-prompt
  codegen (single or swarm) up to N iterations. Accept: a seeded bug is auto-fixed within N. Risk: med.
- **B3 Prompt-injection guard.** `backend/services/prompt_guard.js`: wrap repo/file/RAG content in
  clearly-delimited "untrusted data" blocks + strip instruction-like patterns before it enters
  codegen/orchestrator prompts. Accept: injection test suite passes. Risk: med (security).

### Phase C — Make it high quality
- **C1 Benchmark harness.** `tests/benchmarks/` + a runner that executes the 10 tasks in §9 against
  the live stack and scores each (tests pass / lint / heuristic). Accept: `npm run bench` emits a
  scorecard JSON. Risk: med.
- **C2 Deepen top-20 skills.** Convert highest-value prompt skills to executable with input/output
  schema (zod), tool perms, quality checklist, failure handling, examples, and a test. Files:
  `runtime/skills/forge/definitions`, `runtime/core/skill_registry.py`. Accept: each has a passing
  eval test. Risk: med.
- **C3 Quality/regression scoring in model routing.** Score outputs; prevent weak-model assignment
  on hard tasks; log model→quality. Files: `compute_planner.py`, `model_lanes.py`. Risk: med.
- **C4 Memory closed-loop.** ✅ SHIPPED 2026-06-24. Inject ranked relevant memories/distillations
  into the codegen prompt; provenance-trust gate on retrieval (both Node forge + Python RAG
  surfaces). Files: `forge.js` (`buildContextPack`), `memory_router.py`, new
  `backend/services/memory_trust_gate.js`, `runtime/core/memory_trust.py`,
  `runtime/config/memory_trust.json`, `schema.py` (vector_metadata). Tests: 9 node + 8 py.

### Phase D — Make it powerful
- **D1 Live remote provider adapter** (owner-gated, `COMPUTE_FABRIC_LIVE=1` + creds) so the Phase-7
  registry can actually dispatch to a rented/owned worker. Files: `compute_fabric/index.js` (adapter),
  `remote_worker_registry.js`. Risk: HIGH (secrets/network) — keep deny-by-default.
  > **Progress 2026-06-24 (D1 Phase 1 — secure dispatch foundation SHIPPED):**
  > Unified compute fabric, "never-leak / compute-only" by construction.
  > - **Egress guard** (the spine): `backend/services/egress_guard.js` + `runtime/core/egress_guard.py`,
  >   shared `runtime/config/egress_policy.json`. Classifies every outbound payload
  >   (public<internal<pii<secret) and enforces a tier matrix (local→peer_trusted→
  >   rented_trusted→external_api) deny-by-default + fail-closed: **secrets never leave
  >   the box**, PII/internal redacted, unknown/oversize blocked. Kill-switch `EGRESS_GUARD`.
  > - **Live dispatch adapter**: `backend/compute_fabric/remote_dispatch.js` — turns
  >   `registry.assign()→remote` into a real job sent to a paired peer (laptop/PC) or rented
  >   worker. LIVE-gated + trusted-only + allow-listed endpoint + egress-gated payload +
  >   single-use HMAC job token (per-worker key, only the HASH stored) + size/timeout caps.
  > - **Compute-only isolation**: a worker shares COMPUTE ONLY — the module imports no `fs`/
  >   `child_process` (cannot write/execute); outbound payload + inbound result are structurally
  >   contained (prototype-pollution stripped, depth/size bounded, live objects dropped) so a
  >   compromised/malware worker cannot contaminate or overwrite us. Inbound result is
  >   secret+PII redacted and tagged `_untrusted`.
  > - **Registry hardening**: validated private-LAN/https `endpoint`, per-worker dispatch key
  >   (returned once, hash-only stored, never leaked via list/get), `kind` (peer|rented, default
  >   stricter), remote selection requires an endpoint.
  > - Wired: `POST /api/.../remote-compute/dispatch`. Tests: 17 node + 11 py (deny-by-default,
  >   secret-block, anti-malware containment, compute-only no-fs/exec).
  > **Progress 2026-06-24 (D1 Phase 2 — concurrent multi-provider LLM SHIPPED):**
  > `llm_provider_router.py` rewired: providers run as a fallback chain OR all at once,
  > independently, via `generate_concurrent()` (asyncio.gather; one provider failing/blocked
  > never affects the others). New providers: **OpenAI** (`openai_client.py`) and **NVIDIA
  > hosted NIM** (`nvidia_client.py`, integrate.api.nvidia.com — external extra power for
  > deploying agents) — alongside Anthropic / OpenRouter / Ollama. EVERY external call passes
  > the Python egress guard first (secrets blocked off-box, PII redacted, local Ollama
  > untouched, fail-closed if the guard is unavailable). Tests: 8 py (concurrency isolation,
  > secret-block-before-send, PII-redact, NVIDIA wired+guarded).
  > **REMAINING D1:** live cloud GPU *purchase* adapter (money path — keep HMAC-approval +
  >   dry-run); peer/rented worker-agent daemon (runs the job on the other machine).
- **D2 Extend cache/budget to the Python engine LLM path** (`engine/api.generate`). 
- **D3 Browser/computer-use tasks** behind sandbox+approval (if desired).

---

## Phase E — Goal Achievement System (2026-07-01, plan approved by Lars; execution in progress)

**Reframe (Lars, 2026-07-01):** "the task queue needs to be fully built" → corrected mid-planning:
"this is not a task system, it's a goal-achieving system." Give it a goal → it produces a detailed
plan → it puts agents on the sub-tasks → it must also handle short tasks efficiently → everything
that needs UI wiring must be tracked for the later UI-fixing pass. Full plan, file:line citations,
and open-decision record: `/home/lf/.claude/plans/clever-wandering-dragon.md` (TQ-1..TQ-6).

**What's already there, verified by reading the code, not assumed:** a goal-container already
exists (`forge_cycles`, `forge_store.js:243`; routes `forge.js:5389-5473`) — `POST /projects/:id/
cycles` already does goal→decompose→dependency-aware backlog→cycle→autopilot, it just never writes
progress back (no `run_ids` append, no completion detection, `success_criteria` stored but never
evaluated). A sub-task/child-run schema already exists and is completely unused
(`forge_child_runs`, `forge_store.js:335`, full store API, zero call sites in `forge.js`). The
Decomposer already asks the LLM for `required_skills` per subtask and throws the answer away —
every subtask runs the same generic coder/tester loop regardless of what it needs — while
`runtime/forge/lifecycle/skill_selector.py::select_skills()` (real keyword/tag scoring against the
570-skill library) sits unused for exactly this purpose. Cross-checked against `MASTER_PLAN_V3.md`
Module 7 (`runtime/agents/business_swarm/*` — task_decomposer/assignment_engine/dependency_manager/
parallel_executor/result_aggregator, confirmed **fully built**, 10/10 files, both by my own reading
and independently by PR #335's gap audit): it's the same decompose→assign→parallel-execute→
aggregate shape, currently wired only into `company_planner.py` (business domain) — evaluate
reusing/generalizing it before writing new logic in `forge.js`.

**Three overlapping execution paths consolidate to one:** `forge_queue_item`+`dispatcher.js`
(weakest — becomes an ingestion adapter only, converts to a backlog item instead of executing
directly); **Backlog+Autopilot+Decomposer+Cycles** (the one to build on); `/runs`+`/runs/stream`
(stays as-is — the right tool for small interactive asks).

- **E1 Canonical queue + durable state + finished Cycle lifecycle.** `autopilotSessions`
  (`forge.js:4824`, currently a bare in-process `Map()` — the one real durability gap, everything
  else already persists via SQLite) moves into a new `autopilot_sessions` table in `forge_store.js`.
  `_runAutopilotTick` starts writing back to its Cycle (`run_ids`, completion detection against
  `success_criteria`, `status` transitions). Boot-time reconciliation for anything stuck
  `IN_PROGRESS` after an unclean shutdown. `POST /submit` becomes an adapter into the backlog
  (confirmed: keep this reversible, not a hard cutover). Add `/backlog/:id/cancel|retry`.
- **E2 Goal intake: fast path + agent/skill routing.** A cheap complexity check before the
  Decomposer runs, so trivial asks skip the whole cycle apparatus. Wire the Decomposer's
  `required_skills` into `select_skills()`; route each subtask to a matched skill/specialized agent
  above a confidence threshold, generic pipeline as the unconditional fallback (strict superset —
  nothing that works today stops working). Verify business_swarm reuse here first.
- **E3 Execution capability uplift.** Scoped file read/grep/glob tools for the coder/debug stages
  (closes the single biggest gap vs. a Claude-Code-style loop — currently one-shot "write
  everything" with no ability to read existing content first). Iterative per-file edit-then-verify
  (opt-in, additive). Bounded sub-task delegation via the existing `forge_child_runs` table (depth
  ≤2). Simple rule-based data-dependent branching.
- **E4 Reliability.** A concurrency gate around every local-LLM call site (measured this session:
  4 concurrent forge runs → 2-of-4 Ollama calls failed outright on this 8GB-VRAM box; qwythos:q4
  stays the model per Lars's instruction — this is a hardware/scheduling fix, not a model change).
  Re-tune debug-retry counts against a clean serialized baseline via `tests/benchmarks/
  run_benchmarks.mjs`.
- **E5 UI/observability.** Cycles/Backlog/Autopilot/Decomposer currently have **zero UI surface** —
  confirmed by reading `AscendForgePage.jsx`/`forgeStore.js`. New WS events
  (`forge:cycle_updated`/`backlog_updated`/`autopilot_status_changed`), new tabs, a dependency DAG
  view. **Confirmed:** collapse the three fragmented approval surfaces (global `ApprovalInbox.jsx`,
  `AscendForgePage`'s internal `ApprovalsView`, `ForgeQueueView`'s own approvals tab) into the one
  global inbox, project-filtered.
- **E6 Safety hardening (cross-cutting, checked per-phase, not last).** External submissions and
  delegated sub-tasks must go through the exact same autonomy/high-risk approval gate as any other
  backlog item — no bypass via conversion or delegation. File tools fail loudly on sandbox-escape
  attempts, never silently empty. Concurrency gate fails closed. Baseline-capture + auto-rollback
  stay mandatory-on for every path in the consolidated queue.

**Confirmed decisions (2026-07-01):** adapter mode (not hard cutover) for retiring
`forge_queue_item`/dispatcher; autonomy ceiling stays at the existing default (level 2) for
unattended runs — high-risk changes always pause for approval; approvals UI collapses into the
single global inbox. See the plan file for the full open-decision record and per-phase file lists,
verification steps, and rollback plans.

- **D2 Extend cache/budget to the Python engine LLM path** (`engine/api.generate`). 
- **D3 Browser/computer-use tasks** behind sandbox+approval (if desired).

---

## 14. Questions for Lars

1. **Coding models:** ✅ **ANSWERED 2026-07-01 — qwythos:q4 stays the canonical codegen model.**
   Measured this session: ~60-70% single-shot success on a trivial task, degrades badly under
   concurrent load (fix = Phase E4's concurrency gate, not a model swap). Claude/OpenAI as
   reviewer/planner-only remains open.
2. **Hardware limits:** VRAM/RAM ceiling on your PC, so model routing + swarm agent counts are tuned
   to reality (current swarm default = 5 agents)? *(Partially answered: RTX 2070 Super, 8GB VRAM —
   confirmed live this session; informs Phase E4's concurrency gate default of 1.)*
3. **Remote compute:** do you intend to actually rent (RunPod/Vast) — i.e., should I build the
   D1 live provider adapter — or is owning/pairing your own machines the priority? *(Still open —
   flagged again in Phase E4 as the natural next question once the local concurrency ceiling is
   felt in practice.)*
4. **Autonomy:** ✅ **ANSWERED 2026-07-01 — stays at the current default (level 2)** for
   unattended autopilot/cycle runs. High-risk file changes always pause for approval, even after
   Phase E1's crash-recovery/rollback hardening. Raising it per-project later is Lars's call to
   make explicitly.
5. **Approvals:** ✅ **ANSWERED 2026-07-01 — approval-gated for every write stays current
   behavior**; the three fragmented approval UIs collapse into one surface (Phase E5), but the
   underlying gate itself is unchanged.
6. **First target:** which ONE workflow must be excellent first — (a) fix-a-bug-with-tests on this
   repo, (b) build-a-small-feature, (c) research/summary, (d) security audit?
7. **"Quality output" definition:** for code = "tests pass + lint clean + matches repo style"? For
   non-code = ? (so the benchmark scorer matches your bar.)
8. **Skill priorities:** which ~20 skills matter most to deepen first (engineering? research? sales?)?
9. **UI priority:** one unified operator console, or keep the multi-page cockpit and just add the
   missing status panels?
10. **Security constraints:** is the prompt-injection guard (B3) and a no-secrets-to-cloud rule a
    hard gate before any cloud model use?

---

### Bottom line
The system is **real and now well-connected** (this session closed brain↔forge↔execute, token
efficiency, swarm, and the remote-worker protocol). To make output **high-quality and trustworthy**,
build the **verify→debug→score** loop (Phase B/C-1) and **deepen the top skills** (C2) before adding
more breadth. Start with **B1 (auto test-gate)** + **C1 (benchmark harness)** — they make quality
both *enforced* and *measurable*, which everything else compounds on.

# AI-EMPLOYEE — MASTER PLAN V3

**Status:** PROPOSED (awaiting approval)
**Created:** 2026-06-09
**Supersedes / extends:** `docs/MASTER_PLAN.md` (compute/cluster, Phases 0–8 DONE), `docs/V2_MASTER_PLAN.md` (partly stale), `docs/SYSTEM_CONNECTIVITY_ROADMAP.md`
**Inputs synthesized:** 7 research/plan documents (nr1 avatar rebuild · nr2 perf + companion teammate · nr3 evolution engine · nr4 companion/voice gateway · nr5 UX overhaul + remote/voice/PC-interlink · nr6 AI company-builder vs Polsia · nr7 reference-repo research `research.md`)

---

## Context — why this plan exists

Seven separate plan documents arrived describing months of work. Many assume subsystems that don't exist; many assume subsystems are missing that actually exist and work. This plan is the **single reconciled, sequenced build** grounded in a real codebase audit (2026-06-09), so it is clear what is **done**, what is **partial**, and what is **net-new**.

**Two hard rules carried through every phase:**

1. **External repos in `research.md` are architecture references only.** Extract patterns, interfaces, safety concepts — **no copy-pasting whole external code**. Every borrowed idea is rebuilt natively inside AI-EMPLOYEE with our own contracts, tests, and governance.
2. **No fake data, no silent failures, HITL on all Level-2+ actions, auth on all non-public routes, tests before ship.** (Carried from V2 invariants.)

---

## Audit ground-truth (2026-06-09) — done vs. partial vs. missing

This corrects stale claims in older docs.

### Already REAL and working (do NOT rebuild)

| Subsystem | Evidence |
|---|---|
| **Quantum Cognitive Engine (QCE)** | `runtime/core/quantum/` — 14 files (engine, complexity, oracle, amplifier, interference, router, persistence, reflection, search/orchestrator). Commits e533d862, 6370449e. |
| **10-phase unified pipeline** | `runtime/core/unified_pipeline.py` — all phases present incl. 2.5 context sufficiency. |
| **AgentController** Planner→Executor→Validator | `runtime/core/agent_controller.py` |
| **Model routing** (complexity/wavefield tiers) | `runtime/core/model_routing.py`, `runtime/agents/ai-router/ai_router.py`, `runtime/core/orchestrator.py` LLMClient. Canary/shadow/offline modes. |
| **Memory / RAG / graph** | `runtime/memory/` (router, vector_store, short_term_cache, strategy_store, knowledge_vault, bm25); `runtime/neural_brain/graph/` native SQLite graph + optional Neo4j adapter + sync. |
| **Forge distillation / learning / training** | `backend/services/forge_learning.js` (776L), `backend/services/forge_training.js` (424L), `backend/forge_train.py`, `frontend/.../forge/LearningPanel.jsx` + `TrainingPane.jsx`. Live-wired in `backend/routes/forge.js` (auto distillation records after each run). Tests: `test_phase7_learning.py`, `test_phase8_training.py`. **→ nr3's "distillation already exists, don't duplicate" is CORRECT.** |
| **Deep Research engine** | `runtime/core/deep_research_engine.py` + DDG/Tavily/Wikipedia search in ai_router.py. (Built recently this session.) |
| **Money Mode** (3 real pipelines) | `runtime/core/money_mode.py` — content/lead/outreach with ROI multipliers + HITL. (V2 doc's "len(string)*4" claim is stale.) |
| **Agents** | `runtime/config/agent_capabilities.json` (59+ agents), `backend/agents/index.js` loader. |
| **Ascend Forge** | `backend/routes/forge.js` (44 routes: plan/run/approve/verify/apply/sandbox/sessions/projects/files), Python `ForgeController`, full UI shell. |
| **HITL gate + Approvals** | `runtime/core/hitl_gate.py` (EU AI Act Art.14), `ApprovalInbox.jsx` + `/api/approvals/*`. |
| **Voice** | `backend/api/voice.js`, `backend/core/voice_manager.js`, `backend/services/voice/*` (Fish Speech, Voice Core, Voice Lite, NVIDIA PersonaPlex, STT fallback, persona profiles, streaming). |
| **Compute/cluster** | `MASTER_PLAN.md` Phases 0–8 DONE: ResourceManager, model warming, ComputePlanner, cluster 2FA pairing, Compute Center page + marketplace + owner-approval. |
| **Route auth** | 527 of 563 routes `requireAuth` (94%). (CLAUDE.md "44 of 119" is stale.) |
| **Perf infra (partial)** | `usePerformanceMode.js` tiers; `React.lazy` 20 pages; `vite.config.js` manualChunks (16 vendor + 9 page); Zustand facade with `useShallow` on 9 domain stores. |

### PARTIAL

| Subsystem | Gap |
|---|---|
| **Frontend perf** | 4 `useAppStore()` calls **without selector** (ErrorScreen, TopStrip, PresenceLayer, useOrbitNodeInteraction); **no** `useTransition`/`useDeferredValue`; **no** list virtualization; telemetry writes straight to store every message (only `nb:*` batched). |
| **Telemetry** | `backend/server.js sampleSystemStatus()` generates **fake** GPU temp/usage (sine + cpu factor); has `_realHwCache` fallback hook but **no Python `/api/system/resources` (nvidia-smi/psutil)** populating it. |
| **Remote compute** | Framework + marketplace UI + owner approval exist; **active GPU worker provisioning** (Vast/RunPod execution + artifact sync-back) not live. |
| **Blacklight** | Routes + `blacklight_tools.js` exist; full defensive-skill-OS implementation skeletal. |
| **Progressive disclosure** | `UserExperienceCenter` "perspectives" exist; **no beginner/operator/developer/admin mode toggle**. |

### MISSING (net-new)

| Subsystem | Source plan |
|---|---|
| **Companion/Avatar backend gateway** | nr4 — no `/api/companion/*` or `/api/avatar/*`, no intent router / context resolver / capability registry / execution broker / avatar-state engine. |
| **Evolution Engine control plane** | nr3 — no trace collector / outcome scorer / failure classifier / reflection engine / candidate registry / replay harness / promotion gate. (Distillation exists as the adapter target.) |
| **Avatar visual richness** | nr1 — engine perf-trimmed (rings 13→8, fibers 64→40, 1 halo); needs cinematic restore **keeping** perf wins. |
| **Named model lanes** | nr2/nr7 — FAST/DEFAULT/CODE/REASONING/DEEP layer over existing router + Ollama keep_alive warmup. |
| **AI Company-Builder (CompanyOS)** | nr6 — orchestration layer over existing subsystems. Full design now, build last. |
| **PC interlink / service control** | nr5 — fine-grained local service start/stop/restart. |

---

## Sequenced phases

Ordering principle: **fix what's visibly broken → build the spine everything plugs into → layer features → biggest net-new last.** Each phase has a Definition of Done (DoD).

```
P1  Avatar & Dashboard Truth      (visible quick wins; folds in the existing Dutch dashboard plan)
P2  Frontend Performance Pass     (Zustand selectors, useTransition, WS throttle, virtualization)
P3  Model Lanes & Warmup          (named lanes over real router + Ollama keep_alive)
P4  Companion Gateway — CORE SPINE (intent router, context resolver, capability registry, broker, avatar-state engine)
P5  Voice-First Teammate          (unify voice+chat through gateway; backend-driven avatar states)
P6  Capability Adapters           (Forge, Memory, Money, Security, System, Research → registry)
P7  Evolution Engine              (trace→score→reflect→candidate→replay→promote; distillation as adapter)
P8  UX Overhaul & Modes           (information architecture, progressive disclosure, design system)
P9  Remote/Voice/PC Control Layer (real remote workers, sync-back, service control, compute routing UX)
P10 AI Company-Builder (CompanyOS)(full design now; build as final major phase)
```

---

### P1 — Avatar & Dashboard Truth

**Goal:** Avatar looks like a cinematic intelligence core again (restore quality, keep perf wins), dashboard shows real hardware, dead nav fixed. This is the existing `detailed-plan-full-system-snazzy-fox` dashboard plan, folded in.

- **Real telemetry:** Add Python `/api/system/resources` (nvidia-smi + psutil → gpu_pct, gpu_temp, cpu_temp, vram_free_mb, disk_pct). `server.js _pollRealHardware()` (5s) → `_realHwCache` → `sampleSystemStatus()` returns real values, `gpu_estimated` flag when absent. Files: `runtime/agents/problem-solver-ui/server.py`, `backend/server.js`.
- **Avatar visual restore (keep perf):** In `avatar-engine.js` (+ identical `frontend/public/avatar-engine.js`) restore ring/fiber/iris richness toward cinematic while keeping: halo offscreen cache, idle 30fps cap, no floating orbit particles. Hero size already `clamp(280, 480, 520)` — confirm dominance in center stage. Files: `frontend/src/components/avatar/avatar-engine.js`, `frontend/public/avatar-engine.js`, `CognitiveEye.{jsx,css}`.
- **Avatar reacts to load:** Already wired (NexusOSDashboard.jsx:295-312) — verify against real telemetry (hot temp→alert, high load→executing, busy→thinking; breathing scales with CPU).
- **Top strip + INFRA panel:** Show GPU% + GPU temp (blink red >75°C). `NexusOSDashboard.{jsx,css}`.
- **Fix dead nav:** Quantum Brain already registered in current `Dashboard.jsx` PAGES — verify; SystemTelemetry: hide null cells, show VRAM/disk/py-latency. `SystemTelemetry.jsx`.

**DoD:** GPU temp/usage are real (vary under `ollama run`); avatar visibly richer with no frame drops (DevTools <16ms in executing); top strip + INFRA show 4 real values; no dead sidebar buttons; `npm test` green.

---

### P2 — Frontend Performance Pass

**Goal:** Kill the ~0.5s click/tab lag (nr2).

- **Selector hygiene:** Replace 4 bare `useAppStore()` with field selectors (ErrorScreen, TopStrip, PresenceLayer, useOrbitNodeInteraction); `useShallow` for object/array selectors.
- **Non-blocking nav:** `useTransition` for page switches in `Dashboard.jsx`; `useDeferredValue` for heavy derived lists.
- **WS throttle:** Extend the `nb:*` 100ms batch pattern to `system:status` and other high-freq telemetry (4Hz coalesce) in `useWebSocket.js`.
- **Virtualization:** Add `@tanstack/react-virtual` for long lists (event feed, agent grid, logs, orders).
- **Confirm chunking:** vite manualChunks already good — verify no regressions.

**DoD:** Tab switch <100ms perceived; no full-store re-render on telemetry tick (React DevTools Profiler); long lists virtualized; bundle still <2MB gzip.

---

### P3 — Model Lanes & Warmup

**Goal:** Named lanes over the real router + warm models (nr2/nr7; decision: add lanes on top, don't replace).

- **Named lanes layer:** Map task-type → model atop existing `model_routing.py`: FAST=llama3.2, DEFAULT=gemma3/qwen2.5:7b, CODE=qwen2.5-coder:14b, REASONING=qwen2.5:7b/qwen3.5, DEEP=llama3.3. Lanes resolve to existing tier/wavefield selection — no rewrite of canary/shadow.
- **Ollama warmup:** Confirm/extend `warm_core_models()` (`keep_alive:-1` for llama3.2 + nomic-embed-text) from MASTER_PLAN Phase 5; add per-lane warmup hints.
- **Remove subprocess spawns:** Audit found no `python3 -c` in model path; sweep for any remaining and route through `runtime/engine/api.py`.

**DoD:** Each task type resolves to its lane (logged); hot models stay loaded (no cold-start latency on FAST); routing config hot-reload (`/api/models/reload`).

---

### P4 — Companion Gateway (CORE SPINE)

**Goal:** The missing connective tissue (nr4). Avatar/voice/chat become one control layer; nothing in the frontend calls tools directly. **Decision: core spine, built early.**

New backend modules (native, referencing OpenClaw/Hermes patterns from research.md — not copied):

```
runtime/companion/
  conversation_runtime.py   # listen→understand→retrieve→classify→mode→act→observe→report→learn
  intent_classifier.py      # conversation|analysis|planning|execution|monitoring|debugging|learning|approval
  context_resolver.py       # resolves "this"/"it"/"fix it" from active page + selection + recent events
  capability_registry.py    # typed subsystem capabilities (id, schema, risk L0-L4, requires_approval)
  execution_broker.py       # routes capability calls; streams progress
  safety_gate.py            # read-only free; file/code/deploy/spend require approval
  avatar_state_engine.py    # backend-driven states → companion:avatar_state_changed
  audit_logger.py
backend/routes/companion.js  # POST /api/companion/message (+ streaming), /voice-event, /state, /capabilities
```

- **WS events:** `companion:user_message`, `:thinking_started`, `:plan_created`, `:approval_required`, `:tool_started/progress/finished`, `:avatar_state_changed`, etc.
- **Frontend:** `frontend/src/stores/companionStore.js`, `CompanionShell`/`AvatarStage`/`CompanionChat`/`ApprovalCard`, `useCompanionSocket.js`. Existing `/api/chat` keeps working; companion is the new spine other phases plug into.

**DoD:** "What is the system doing?" via chat returns real status through the gateway; avatar state changes from real backend events (not frontend timers); risky actions produce approval cards; existing chat unbroken.

---

### P5 — Voice-First Teammate

**Goal:** Voice as a first-class gateway into the same runtime (nr4 §6).

- Route STT final transcripts + TTS through the companion gateway (reuse existing voice services).
- Barge-in / stop / cancel / pause / continue; push-to-talk + optional wake.
- Spoken output concise; detailed output to chat/action panel.
- Avatar voice states (listening/thinking/speaking/interrupted) driven by `avatar_state_engine`.

**DoD:** Hands-free "what's running?" answered; interruptible TTS; avatar reflects voice state; latency targets (partial transcript <150ms, state change <100ms).

---

### P6 — Capability Adapters

**Goal:** Every major subsystem registers typed capabilities so the companion routes dynamically instead of one giant prompt (nr4 §4, nr7 capability map).

Adapters (read-only first, then write w/ approval):
- **System Health** (status, logs, tasks) — L0
- **Memory** (search, write_structured, project context) — L0/L1
- **Research** (deep research start/get) — L1
- **Money Mode** (analyze idea, create plan) — L1, execution L3
- **Forge** (index, search_code, plan_change, run_tests, review_diff → L0/L1; apply_patch/merge → L3)
- **Security/Blacklight** (score_action, audit_event, scan) — gated

**DoD:** `/api/companion/capabilities` lists capabilities w/ risk levels; companion picks correct subsystem for a request; write capabilities gated through `safety_gate` + HITL.

---

### P7 — Evolution Engine

**Goal:** Closed measured self-improvement loop (nr3). **Distillation already exists (Forge Phase 7/8) → wire as adapter, do not duplicate.**

```
runtime/evolution/
  trace_collector.py    # async/batched; <5ms append; secret redaction
  trace_store.py        # JSONL → SQLite; ~/.ai-employee/evolution/
  outcome_scorer.py     # quality/speed/safety/cost/completion + hard signals
  failure_classifier.py # missing_context|bad_tool_choice|planning_error|...
  reflection_engine.py  # only on fail/high-value; compact typed lessons
  candidate_registry.py # prompt_patch|router_rule|skill_patch|distillation_dataset...
  replay_harness.py     # benchmark cases from real traces; before/after compare
  promotion_gate.py     # quality_delta≥0.03, speed regression≤5%, safety≥0.98, human approval for high-impact
  rollback_manager.py
  distillation_adapter.py  # → backend/services/forge_learning.js + forge_training.js (EXISTING)
backend/routes/evolution.js  # /api/evolution/status|traces|lessons|candidates|.../promote|rollback
```

- Lightweight trace hooks in QCE planner/executor (non-blocking; `EVOLUTION_ENABLED=false` disables).
- Reflection/replay/distillation run async/offline only — never block live path.
- **Evolution Center UI:** live traces, lessons, candidates, replay results, promotion gate, rollback history.

**DoD:** trace per task w/ minimal overhead; failed tasks get lessons + failure type; candidates testable before activation; promotion only on passing gates; rollback works; distillation feeds existing Forge pipeline (no second distiller).

---

### P8 — UX Overhaul & Modes

**Goal:** Operational cockpit for normal + power users (nr5).

- **Information architecture:** Reduce sidebar sprawl (currently 5 groups × 30 items, many duplicates → SecurityPanel ×3, SystemHealthPage ×4). Merge duplicates; group logically.
- **Progressive disclosure:** Beginner / Operator / Developer / Admin modes — per-mode visibility, extra confirmation on advanced actions. Build on existing `UserExperienceCenter` perspectives.
- **Companion-first dashboard:** central avatar zone + command/voice input + active tasks + system status + approvals + recent results + quick actions.
- **Design system:** colors, type scale, spacing, card/button/badge/modal/toast/empty/loading/error patterns. Reusable components from nr5 expanded list (CompanionPanel, TaskTimeline, LocalRemoteTaskMap, ComputeControlPanel, DataSyncPanel, VoiceControlPanel, ApprovalQueue, SafetyGateModal, EmptyState, LoadingSkeleton, ErrorRecoveryPanel, …).
- **Page-by-page audit:** keep / merge / split / redesign / remove / move-to-advanced per page (47 pages).

**DoD:** new IA with fewer top-level items; mode toggle works (beginner hides advanced); every page has empty/loading/error states; design tokens applied consistently; no functionality lost.

---

### P9 — Remote / Voice / PC Control Layer

**Goal:** Make local/remote/voice/compute a unified, visible operational layer (nr5 extra context).

- **Real remote workers:** Provision (Vast/RunPod), stream status, **sync artifacts/logs back locally** (local = source of truth), recover from remote shutdown, track cost. Extends existing Compute Center framework.
- **Compute routing UX:** per-task target (local/remote/hybrid/auto) + reason + cost + privacy impact + fallback + live status + sync status. RemoteKillSwitch, PrivacyModeToggle.
- **PC interlink / service control:** fine-grained start/stop/restart of local services (Node, Python, Ollama, Neo4j), driver/GPU status, port map — gated.
- **Data sync panel:** which outputs are local vs pending sync, snapshots, rollback points, failed-sync warnings.

**DoD:** user sees local vs remote at a glance; can start/stop remote safely w/ kill switch; remote outputs sync back; service control works; costs/privacy shown before execution.

---

### P10 — AI Company-Builder (CompanyOS)

**Goal:** Beat Polsia (nr6). **Decision: full design now, build last.** Reframed as an **orchestration layer over existing subsystems** (Money Mode, Forge, agents, HITL, research, memory) — minimal duplication.

Full design captured (build deferred to final phase):
- **CompanyOS core** (company/project entities, lifecycle), **Founder Intake** (clarifying Q's → brief), **Validation Engine** (market/competitor/demand scoring — *validate before building*, our edge over Polsia), **Company Planner**, **Agent Team Orchestrator** (CEO/CTO/Product/Marketing/Growth/Sales/Support/Finance/Security roles mapped to existing agents), **Task Cycle Engine** (recurring loops + approval checkpoints), **Build integration** (Forge sandbox/worktree), **Marketing/Support/Metrics engines**, **Approval & Safety** (autonomy L0-L4: observe/draft/safe-local/approved-external/budget-bounded), **Memory graph**, **Avatar/voice command**, **Remote compute router**, **Export/ownership layer** (full local export, no lock-in — our edge).
- Data models (Company, FounderBrief, ValidationReport, Roadmap, AgentAssignment, TaskCycle, ApprovalRequest, MetricSnapshot, ExportPackage, …), API surface, UI cockpit pages — detailed in nr6; implement after P1-P9.

**Polsia-beating differentiators (non-negotiable):** local-first ownership · full exportability · transparent agent reasoning/action logs · validation-before-build · human approval gates for spend/publish/email/deploy/core-mod · memory-graph linkage · avatar/voice as central command · remote compute that syncs back · sandbox before real changes.

**DoD:** user creates a company via intake → validation report → approved MVP plan → tasks via existing agents → sandboxed build → approval-gated marketing → metrics tracked → full export. Nothing autonomous spends/sends/deploys without approval.

---

## Reference-repo integration map (research.md — patterns only, no code copy)

| Native target | Inspired by (reference only) | Lands in phase |
|---|---|---|
| Named model lanes / arena | 9router, pi, goose, GODMOD3 (safe parts) | P3 |
| Companion gateway / multi-channel | openclaw-2.0, Hermes | P4/P5 |
| Capability registry / MCP-style contracts | MCP spec, hexstrike (governed) | P6 |
| Evolution loop | Reflexion, Voyager, Self-Refine, DSPy, automaton (governed, **no self-replication**) | P7 |
| Context DB / memory tiers | OpenViking, turbovec, MemGPT | P7/P8 (memory adapter) |
| UI quality gate | taste-skill | P8 |
| Content/creative/voice factory | MoneyPrinterTurbo, Fooocus, VoxCPM, yt-dlp | P10 |
| Business swarm | openclaw-2, financial-services | P10 |
| Defensive security skill OS | Anthropic-Cybersecurity-Skills, hexstrike (defensive only) | P9/P10 |

**Excluded by safety policy:** autonomous self-replication (automaton), offensive/unauthorized security automation, jailbreak/prompt-bypass (GODMOD3), voice cloning without consent.

---

## Cross-phase invariants

1. No fake data — real or explicit offline state.
2. No silent failures — logged, surfaced, recoverable.
3. HITL on all L2+ actions — no autonomous spend/send/deploy/core-mod.
4. Auth on all non-public routes.
5. External repos = reference only, rebuilt natively.
6. Heavy learning/distillation/replay = async/offline, never blocks live path.
7. Tests before ship; each phase meets its DoD before the next starts.

---

## Status of older docs after this plan

- `docs/MASTER_PLAN.md` — **current/accurate** for compute & cluster (Phases 0–8 DONE, Phase 9 revenue NEXT). Kept; P9 here extends it.
- `docs/V2_MASTER_PLAN.md` — **partly stale** (money-mode + route-auth claims outdated). Useful security/testing/observability phases folded into invariants + relevant phases.
- `docs/SYSTEM_CONNECTIVITY_ROADMAP.md` — connectivity targets absorbed into P4/P6.

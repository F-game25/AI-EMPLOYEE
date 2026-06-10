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
P9.5 Hybrid Rust Performance       (profile-driven native rewrite of proven hot paths; keep Tauri shell)
P10 AI Company-Builder (CompanyOS)(full design now; build as final major phase)
```

> **Profiling starts early:** P2 (Frontend Perf) and P9 (compute layer) instrument the hot paths. P9.5 only rewrites what profiling proves is a bottleneck — no premature Rust.

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

### P3 — Model Tiers & Warmup — DONE (bc727051, 56ee3443)

**Goal:** Hardware-dynamic tiers over the real router + warm models + paid execution targets.

- **Tiers (FINAL names):** `FAST / NORMAL / HEAVY / DEEP_THINKING` size tiers + a separate `CODE` tier. **Nothing is a fixed LLM** — each tier is a candidate ladder; `resolve_tier` picks the biggest model that fits the live VRAM budget (ResourceManager), with CPU-offload headroom. `CODE` is ALWAYS a coder model (qwen2.5-coder 32b/14b/7b/3b/1.5b by VRAM) — never degrades to llama. `DEEP_THINKING` reaches for the biggest model the box supports (70b/32b on big GPUs). Env `MODEL_TIER_<NAME>` overrides. (`runtime/core/model_lanes.py`)
- **Execution targets (paid, user-approved):** `resolve_target(tier, prefer, allow_paid)` returns `local` (free, default), `external_api` (Claude/GPT — paid), or `rented_remote` (rent a GPU to run a much bigger local model — paid). CODE/HEAVY/DEEP can upgrade to external API or rented compute. **Paid targets are never auto-selected** — they require `allow_paid` and are flagged `requires_approval+requires_payment`, cleared by SafetyGate/HITL + the compute-fabric estimate→approve→provision flow. `upgrade_options(tier)` lets the UI offer them.
- **Warmup:** `warm_core_models()` keeps FAST+NORMAL resident (`hot_tier_models`), hardware-resolved; falls back to static core list if tiers unavailable.

**DoD:** ✅ tiers resolve hardware-dynamically; CODE always coder; paid external/rented paths gated; hot models warmed; 13 tests pass.

---

### P4 — Companion Gateway (CORE SPINE) — DONE (285ad957)

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

### P5 — Voice-First Teammate — DONE (2bd67875)

**Goal:** Voice as a first-class gateway into the same runtime (nr4 §6).

- Route STT final transcripts + TTS through the companion gateway (reuse existing voice services).
- Barge-in / stop / cancel / pause / continue; push-to-talk + optional wake.
- Spoken output concise; detailed output to chat/action panel.
- Avatar voice states (listening/thinking/speaking/interrupted) driven by `avatar_state_engine`.

**DoD:** Hands-free "what's running?" answered; interruptible TTS; avatar reflects voice state; latency targets (partial transcript <150ms, state change <100ms).

---

### P6 — Capability Adapters — DONE (6a26fe55)

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

### P7 — Evolution Engine — DONE (a0bcb6c6)

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

### P8 — UX Overhaul (ONE auto-adapting system — NO manual modes)

**Goal:** Operational cockpit that is **one system which auto-adjusts to the user's PC**. (nr5)

**DECISION (corrected):** Manual beginner/operator/developer/admin **mode toggles are REMOVED from scope.** The user-mode idea predates hardware recognition; now it's redundant. The system already auto-detects hardware (`runtime/engine/compute/resource_manager.py` + `frontend/src/hooks/usePerformanceMode.js` tier high/medium/low from cores/RAM/GPU, applied via root `data-perf`) and scales models (`model_lanes` VRAM-dynamic). UX adapts **automatically to specs**, not to a manual complexity switch.

- **Auto-adaptation (already the foundation):** keep + lean on `usePerformanceMode` (auto tier) + `data-perf` CSS; heavier panels/visuals downgrade themselves on weak hardware. No user-facing complexity toggle.
- **Information architecture:** Reduce sidebar sprawl (5 groups × 30 items, many duplicates → SecurityPanel ×3, SystemHealthPage ×4). Merge duplicate routes; group logically. (Role/perspective for *job focus* may stay via existing `UserExperienceCenter` — but that's a view filter, not a capability gate.)
- **Companion-first dashboard:** central avatar zone + command/voice input + active tasks + system status + approvals + recent results + quick actions.
- **Design system:** colors, type scale, spacing, card/button/badge/modal/toast/empty/loading/error patterns. Reusable components (CompanionPanel, TaskTimeline, LocalRemoteTaskMap, ComputeControlPanel, DataSyncPanel, VoiceControlPanel, ApprovalQueue, SafetyGateModal, EmptyState, LoadingSkeleton, ErrorRecoveryPanel, …).
- **Page-by-page audit:** keep / merge / split / redesign / remove per page (47 pages).

**DoD:** one system, no manual mode toggle; UI density/visuals auto-scale to detected hardware; fewer duplicate top-level nav entries; every page has empty/loading/error states; design tokens applied consistently; nothing lost.

---

### P9 — Remote / Voice / PC Control Layer

**Goal:** Make local/remote/voice/compute a unified, visible operational layer (nr5 extra context).

- **Real remote workers:** Provision (Vast/RunPod), stream status, **sync artifacts/logs back locally** (local = source of truth), recover from remote shutdown, track cost. Extends existing Compute Center framework.
- **Compute routing UX:** per-task target (local/remote/hybrid/auto) + reason + cost + privacy impact + fallback + live status + sync status. RemoteKillSwitch, PrivacyModeToggle.
- **PC interlink / service control:** fine-grained start/stop/restart of local services (Node, Python, Ollama, Neo4j), driver/GPU status, port map — gated.
- **Data sync panel:** which outputs are local vs pending sync, snapshots, rollback points, failed-sync warnings.

**DoD:** user sees local vs remote at a glance; can start/stop remote safely w/ kill switch; remote outputs sync back; service control works; costs/privacy shown before execution.

---

### P9.5 — Hybrid Rust Performance

**Goal:** Recode the proven-hot paths in Rust for native speed, keeping Python/Node for everything else. **Evidence-driven — never rewrite what isn't a measured bottleneck.**

**Status today (audit):** `src-tauri/` (Tauri desktop shell — `lib.rs`, `main.rs`, `Cargo.toml`) is REAL and shipping. The broader "hybrid Rust optimisation/recode" was started conceptually (Tauri app) but the *hot-path native modules* were never built. `research.md` references `vix` (C++ runtime) and native modules (`native/vector_search_service/`, `audio_processing_service/`, `browser_orchestration_service/`) as deferred. This phase makes it explicit.

**Approach (in order):**
1. **Profile first** — use the instrumentation from P2 (frontend) + P9 (compute) + add Python/Node timing on: vector search/RAG retrieval, embedding, browser orchestration, audio/TTS processing, JSON state I/O under load. Produce a ranked bottleneck list with real numbers.
2. **Rewrite only proven-hot paths** as native Rust modules behind a stable FFI/IPC boundary (PyO3 for Python-callable, or a local service the Node/Python side calls). Candidates, by likelihood: local vector index/search (turbovec-style), browser orchestration service, audio processing. Keep the Python/Node API identical so callers don't change.
3. **Keep the Tauri shell as-is** — don't rewrite the desktop launcher; extend it only if it owns a hot path.
4. **Each rewrite is reversible** — feature-flag the native path, fall back to the Python/Node implementation, A/B the latency, promote only if it's faster AND passes the same tests.

**Reference (patterns only, no copy):** `turbovec`/TurboQuant (vector index), `vix` (native runtime structure), `agent-browser` (Rust browser CLI). Rebuilt natively per the no-copy rule.

**DoD:** a ranked bottleneck report exists; at least the top bottleneck has a native module behind a flag that beats the Python/Node version on latency with equal correctness (same tests pass); fallback works; no caller API changed.

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

> **Detailed expansion:** every row above is broken out into a buildable, reconciled capability phase in **§ Reference-Capability Layers** (below). (Source research lives at `/home/lf/Downloads/research.md`.)

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

---

## Reference-Capability Layers (research.md — native rebuilds)

> **Source:** `research.md` (28 reference repos, at `/home/lf/Downloads/research.md`). **Hard rule (carried from this plan's rule #1):** external repos are **reference architecture only** — extract patterns/interfaces/safety concepts, **rebuild natively** inside AI-EMPLOYEE. **No copy-pasting whole external systems.** This appendix expands the integration map above into reconciled, buildable capability phases. Each entry is marked **DONE / PARTIAL / NEW** against the 2026-06-09 audit; DONE/PARTIAL items cross-reference P1–P10 instead of re-planning.

### Capability-status table

| # | Capability | Reference repo (patterns only) | Status | Native location | Slots into |
|---|---|---|---|---|---|
| — | Model/Provider Router (named lanes, targets, providers) | 9router, pi, goose | **DONE** | `runtime/core/model_lanes.py`, `model_routing.py`, `runtime/agents/ai-router/ai_router.py` | P3 |
| — | Avatar/Companion Gateway (multi-channel spine) | openclaw-2.0 | **DONE** | `runtime/companion/*`, `backend/routes/companion.js` | P4/P5 |
| — | Capability adapters (system/memory/research/money/forge/security) | MCP spec, hexstrike (governed) | **DONE** | `runtime/companion/execution_broker.py` | P6 |
| — | Distillation / self-improvement training | automaton (governed), cashclaw (study) | **DONE** (adapter target for P7) | `backend/services/forge_learning.js`, `forge_training.js`, `backend/forge_train.py` | P7 |
| — | Remote compute (rent GPU) | vix (perf), goose | **DONE/PARTIAL** | `backend/compute_fabric/`, `runtime/engine/compute/compute_planner.py` | P9 |
| 1 | **Browser Execution Service** | agent-browser | **NEW** | `runtime/tools/browser/` | extends P6 |
| 2 | **Context Database Layer** | OpenViking, turbovec | **NEW** (on existing vector_store+bm25) | `runtime/memory/context_db/` | P7/P8 memory |
| 3 | **Skill Lifecycle OS (Forge)** | agent-skills, taste-skill | **NEW** (formalizes Forge Phase5–9) | `runtime/forge/lifecycle/`, `runtime/forge/ui_quality/` | extends Forge / P8 |
| 4 | **Work Acquisition + Delivery Engine** | cashclaw | **PARTIAL-upgrade** (on money_mode) | `runtime/money/work_engine/` | upgrades P10 MoneyMode |
| 5 | **Content Factory + Creative Studio + Voice + Media Intake** | MoneyPrinterTurbo, Fooocus, VoxCPM, yt-dlp | **NEW** | `runtime/content/`, `runtime/voice/`, `runtime/media/` | P10 CompanyOS |
| 6 | **FinanceOps Module** | financial-services | **NEW** | `runtime/finance/` | P10 CompanyOS |
| 7 | **Business Swarm Layer** | openclaw-2 | **PARTIAL-upgrade** (on 59-agent catalog) | `runtime/agents/business_swarm/` | P10 CompanyOS |
| 8 | **Research Quality Engine** | academic-research-skills | **PARTIAL-upgrade** (on deep_research_engine) | `runtime/research/quality/` | extends P7 |
| 9 | **Blacklight Defensive Skill OS** | Anthropic-Cybersecurity-Skills, hexstrike (defensive) | **PARTIAL-upgrade** (on blacklight) | `runtime/security/skills/`, `runtime/security/tools/` | P9/P10 |
| 10 | **Harness Compatibility Layer + Dev Kit** | ECC, goose, pi | **NEW** | `runtime/harness/`, `tools/ai_employee_cli/` | P8/P10 packaging |
| 11 | **Reference Learning Library** | build-your-own-x | **NEW** (context-only) | `runtime/learning/reference_library/` | feeds Skill OS / Forge |
| 12 | **Model Arena Mode** | GODMOD3 (SAFE parts only) | **NEW** | `runtime/core/arena/` | extends P3 + feeds P7 |

**Counts:** DONE 4 (+1 DONE/PARTIAL compute) · PARTIAL-upgrade 4 · NEW 7.

> Deferred/excluded from research.md: native C++ runtime (`vix`) → folded into **P9.5 Hybrid Rust** (profile-first); web crawler (`scrapy`, repo unverified) → deferred behind Browser Exec + robots/rate-limit gating; `pi` sandbox/state patterns → already covered by Forge sandbox + `safety_gate.py`.

### Module 1 — Browser Execution Service  *(NEW — extends P6)*
- **Ref:** agent-browser (stable refs, accessibility-tree snapshots, action contracts). **Builds on:** existing `runtime/browsers/playwright` + CloakBrowser — adds the agent-facing tool service, doesn't replace Playwright.
- **Paths:** `runtime/tools/browser/{browser_service,browser_session,tool_contracts,accessibility_snapshot,action_executor,screenshot_service,browser_sandbox,browser_events}.py`; `backend/routes/browser.js`; registered as a companion capability.
- **Interfaces:** `open(url,profile) -> session_id`; `snapshot(s) -> {tree,refs}`; `act(s,action,ref,value)`; `extract(s,kind,ref)`; `capture(s,kind)`; `eval(s,js)` (read-only default). WS: `browser:status/action_started/finished/approval_required`.
- **Governance:** nav/snapshot/extract = L0 free; **L3 approval** for submit/purchase/account-change/outreach/download/writing eval. Sandboxed per-task profiles; every action logs snapshot+screenshot.
- **DoD:** open→snapshot→click-ref→screenshot read path free; side-effecting actions produce approval cards; profile isolation verified.

### Module 2 — Context Database Layer  *(NEW — on existing retrieval; P7/P8)*
- **Ref:** OpenViking (filesystem context, L0/L1/L2, retrieval trajectories) + turbovec (hybrid retrieve, stable IDs, allowlist). **Builds on** `vector_store.py`/`bm25.py`/`memory_router.py` — does NOT replace them.
- **Paths:** `runtime/memory/context_db/{context_tree,context_node,context_loader,recursive_retriever,retrieval_trace,session_compressor,memory_writer,context_permissions}.py`; `backend/routes/context.js`.
- **Tree:** `/project/{goals,decisions,tasks,code,skills,memory,reports,feedback}` + `/user/{preferences,goals,constraints}`.
- **Interfaces:** `retrieve(query,project,levels,filters) -> {nodes,trace}`; `compress_session(s) -> memory_refs`; `write(path,content,validate)`; `delete(path)`.
- **Governance:** retrieval read-only; writes validated; tenant/project ACL via allowlist; **trace always returned** (debuggable); exact-search fallback for critical scopes.
- **DoD:** tiered nodes + visible trace using existing stores (no 2nd store); session compression → durable memory; ACL respected.

### Module 3 — Skill Lifecycle OS for Forge  *(NEW — formalizes Forge Phase5–9 / P8)*
- **Ref:** agent-skills (spec→plan→build→test→review→simplify→ship, auto-select) + taste-skill (UI quality, anti-slop, image-to-code, no-placeholder). **Builds on** existing Forge routes/controller/sandbox.
- **Paths:** `runtime/forge/lifecycle/{spec,planning,implementation,test,review,simplify,ship}_engine.py + skill_selector.py + acceptance_criteria.py`; `runtime/forge/ui_quality/{ui_auditor,design_language_inferer,component_quality_checker,image_to_code_pipeline,frontend_preflight}.py`.
- **Interfaces:** `select_skills(task,type,risk,max) -> [skill]`; `run_lifecycle(goal) -> {spec,acceptance,plan,slices,tests,review,ship_checklist}` (machine-checkable per stage); `ui_audit(target) -> {design_map,violations,placeholders}`.
- **Governance:** plan/spec/review/tests L0/L1; `apply_patch`/merge stays **L3** (already enforced). Anti-rationalization gate blocks ship until criteria+tests pass; UI gate blocks placeholders.
- **DoD:** full spec→ship lifecycle with gate per stage; skill auto-select works; UI gate fails a placeholder build; apply still approval-gated.

### Module 4 — Work Acquisition + Delivery Engine  *(PARTIAL-upgrade on money_mode; P10)*
- **Ref:** cashclaw. **Builds on** `runtime/core/money_mode.py` + approvals/HITL — lifecycle upgrade, not replacement.
- **Paths:** `runtime/money/work_engine/{opportunity_ingestion,fit_evaluator,pricing_estimator,work_task_lifecycle,client_message_engine,deliverable_builder,submission_queue,feedback_collector,study_session_runner,money_memory}.py + marketplace_adapters/`.
- **Lifecycle (external steps approval-gated):** found → eval(fit/value/risk) → quote → **approve** → execute → stage → **approve** → submit → feedback → study.
- **Governance:** **no autonomous client messaging / marketplace action / wallet movement without approval.** Anti-spam throttle. Study loop feeds P7/Forge distillation, async only.
- **DoD:** opportunity → eval → quote → (approve) → execute → stage → (approve) → submit with two hard gates; feedback stored; offline study lessons.

### Module 5 — Content Factory + Creative Studio + Voice + Media Intake  *(NEW — P10)*
- **Ref:** MoneyPrinterTurbo, Fooocus, VoxCPM, yt-dlp. **Builds on** existing voice services for TTS plumbing.
- **Paths:** `runtime/content/video/*`, `runtime/content/image/*`, `runtime/voice/{tts_router,voice_design,voice_clone_gate,streaming_tts,avatar_voice_controller}.py`, `runtime/media/{media_intake_service,source_permission_checker,transcript_extractor,subtitle_service,media_to_memory_pipeline}.py`.
- **Interfaces:** `make_video(brief) -> {assets,draft,publish_request}`; `gen_image(prompt,style)`; `synthesize(text,voice)`; `clone_voice(ref,consent_token)`; `ingest_media(url,rights_token) -> {transcript,metadata}`.
- **Governance:** **all publish/post approval-gated** (publish_queue stages, never auto-posts). **Voice cloning only with consent token; synthetic voice labeled.** Media only with rights confirmation + license metadata. No face cloning/impersonation.
- **DoD:** topic→script→assets→TTS→subtitles→rendered draft staged (not posted); image+brand assets; consented clone gated; media ingest with license metadata.

### Module 6 — FinanceOps  *(NEW — P10, advisory only)*
- **Ref:** financial-services. **Paths:** `runtime/finance/{finance_agent_registry,business_model_builder,market_researcher,financial_model_drafter,pricing_analyzer,pitch_memo_builder,revenue_forecaster,human_review_gate}.py`.
- **Interfaces:** `draft_business_model`, `draft_financial_model`, `price_analysis`, `build_pitch_memo` — **all return `requires_human_signoff`**.
- **Governance:** **advisory only.** No transaction/trade execution, no final tax/legal/accounting advice. All staged through human_review_gate. Feeds P10 Validation Engine.
- **DoD:** cashflow/pricing/comps/memo drafts marked advisory + sign-off; no money/trade action executable.

### Module 7 — Business Swarm Layer  *(PARTIAL-upgrade on 59-agent catalog; P10)*
- **Ref:** openclaw-2. **Builds on** `agent_capabilities.json` + `backend/agents/index.js` — formalizes contracts; P10 orchestrator consumes it.
- **Paths:** `runtime/agents/business_swarm/{registry,capability_profiles,task_decomposer,assignment_engine,parallel_executor,dependency_manager,result_aggregator,agent_contracts}.py`.
- **Contract:** `{id,capabilities[],tools_allowed[],memory_scope[],risk_level,requires_approval_for[],output_contract,success_metrics,escalation_rules}`.
- **Governance:** no fake autonomy — real tools/memory/metrics/contracts per agent. Risky caps → `requires_approval_for` → HITL; tool perms via `safety_gate.py`.
- **DoD:** each agent has a typed contract; goal decompose→assign→parallel→aggregate; approval-gated caps can't fire without HITL.

### Module 8 — Research Quality Engine  *(PARTIAL-upgrade on deep_research_engine; extends P7)*
- **Ref:** academic-research-skills. **Builds on** `deep_research_engine.py` + search.
- **Paths:** `runtime/research/quality/{research_planner,source_collector,source_verifier,claim_auditor,citation_anchor,integrity_gate,reviewer_panel,report_builder,material_passport}.py`.
- **Interfaces:** `plan(topic)`; `verify_source(ref) -> {valid,provenance}`; `audit_claims(draft) -> {anchored,unsupported,fabricated}`; `review_panel(report)`; `integrity_gate(report) -> pass|block`.
- **Governance:** **no hallucinated sources** — verified sources separated from reasoning; fabricated-ref detection blocks ship; reproducibility metadata attached. Heavy review async.
- **DoD:** report carries citation anchors, claim audit (no unsupported/fabricated through gate), review scores, reproducibility metadata.

### Module 9 — Blacklight Defensive Skill OS  *(PARTIAL-upgrade on blacklight; P9/P10)*
- **Ref:** Anthropic-Cybersecurity-Skills (progressive disclosure, MITRE/NIST/ATLAS/D3FEND), hexstrike (defensive parts: registry, risk cards, process mgmt). **Builds on** existing blacklight tools/routes.
- **Paths:** `runtime/security/skills/{security_skill_registry,skill_frontmatter_index,framework_mapper,security_skill_loader,defensive_workflow_runner,verification_engine,report_templates,scope_gate}.py`; `runtime/security/tools/{security_tool_registry,tool_scope_validator,process_manager,risk_card_generator,authorization_gate}.py`.
- **Skill contract:** `{skill_id,domain,allowed_use:"defensive_authorized",frameworks{...},requires_scope:true,requires_approval:true,verification_steps[]}`.
- **Governance:** **defensive/authorized only.** Default = defensive analysis/lab/internal hardening/remediation. **Active scans require signed scope + ownership + approval** (scope_gate + authorization_gate). No offensive automation, no exploit generation as autonomous feature.
- **DoD:** progressive discovery returns framework-tagged defensive skills; active scan blocked without signed scope + approval; defensive report templates with MITRE/NIST mappings.

### Module 10 — Harness Compatibility Layer + Dev Kit  *(NEW — P8/P10 packaging)*
- **Ref:** ECC, goose, pi. **Paths:** `runtime/harness/{harness_registry,claude_exporter,codex_exporter,cursor_exporter,opencode_exporter,gemini_exporter,copilot_exporter,rules_compiler,hook_manager,mcp_config_generator}.py`; `tools/ai_employee_cli/{start,stop,doctor,task,agent,logs,install-extension,export-config}`; `runtime/extensions/{extension_registry,mcp_adapter,install_manager,permission_manifest,extension_health}.py`.
- **Interfaces:** `export(harness,profile) -> config_bundle` (one canonical source → per-harness); `install_extension(manifest)`; CLI `doctor`.
- **Governance:** **one canonical internal source** — export, never hand-maintain copies. **Secrets never in exported prompts/configs.** Extension installs permission-reviewed; diagnostics scrub secrets.
- **DoD:** export to Claude Code/Codex/Cursor produces valid secret-free configs from one source; CLI works; extension install permission-gated.

### Module 11 — Reference Learning Library  *(NEW — context-only; feeds Skill OS/Forge)*
- **Ref:** build-your-own-x. **Paths:** `runtime/learning/reference_library/{guide_index,architecture_patterns,first_principles_planner,build_template_generator,skill_recommender,forge_reference_loader}.py`.
- **Interfaces:** `find_patterns(tech) -> [pattern]`; `plan_from_first_principles(target) -> build_plan`; consumed by Forge Skill OS.
- **Governance:** **context-only, not a runtime dependency.** Sources validated; used as research context, never direct code source (no-copy rule).
- **DoD:** Forge queries a pattern for a build target → first-principles plan; read-only reference, no runtime coupling.

### Module 12 — Model Arena Mode  *(NEW — extends P3, feeds P7)*
- **Ref:** GODMOD3 — **SAFE parts only** (multi-model race, composite scoring, context-adaptive sampling, EMA feedback). **EXCLUDE** jailbreak/prompt-bypass/refusal-evasion/obfuscation. **Builds on** `model_lanes.py`/`model_routing.py`.
- **Paths:** `runtime/core/arena/{model_race,output_scorer,routing_feedback,sampling_autotune,response_normalizer,model_benchmark_store}.py`.
- **Interfaces:** `race(prompt,models,constraints) -> [responses]`; `score(responses) -> ranked` (transparent); `learn(result) -> routing_pref_update` (feeds router + P7).
- **Governance:** transparent scoring; racing is **cost-aware** (gated by `allow_paid` + budget) and opt-in; **no bypass features.**
- **DoD:** arena races N models, transparent composite ranking, picks best, updates routing pref within budget gates; no bypass behavior.

### 3-phase implementation order (mirrors research.md)
- **Phase 1 — Capability foundation:** Browser Exec (1), Context DB (2), Skill Lifecycle OS (3); *Model Router DONE (P3); Companion Gateway DONE (P4/P5).*
- **Phase 2 — Money / real-world:** Work Engine (4), Content Factory+Creative+Voice+Media (5), Analytics dashboards (PARTIAL-upgrade on `runtime/core/observability/*`), FinanceOps (6), Business Swarm (7).
- **Phase 3 — Self-improve / security / packaging:** Evolution Engine (*P7*; Research Quality Engine (8) extends it), Blacklight Skill OS (9), Harness Compat (10), Reference Library (11), Model Arena (12).

### Explicit EXCLUSIONS (non-negotiable)
- No whole-system copying — reference only, rebuilt natively with own contracts/tests/governance.
- No autonomous self-replication (automaton) — propose, humans approve.
- No unapproved/unauthorized security scanning — active scans require signed scope + ownership + approval; default defensive only; no autonomous exploit generation.
- No financial transaction execution — FinanceOps advisory; no trade/payment/wallet movement; human sign-off.
- No jailbreak/prompt-bypass/refusal-evasion/obfuscation (GODMOD3) — safe eval ideas only.
- Voice cloning only with explicit consent; synthetic voice labeled; no impersonation.
- No autonomous external send/spend/publish/post/deploy — gated through `safety_gate.py` + HITL (invariant #3).
- No fake autonomy — every swarm agent has real tools/memory/metrics/contracts.

# AI-EMPLOYEE Gap Analysis — 2026-06-30

**Branch:** `claude/gap-analysis-deep-dive-twiozu`  
**Against:** `docs/MASTER_PLAN_V3.md` (audited 2026-06-09, all phases P1–P10 + Modules 1–12)  
**Method:** Full filesystem audit against every path, file, and DoD listed in the plan.

---

## TL;DR — Status matrix

| Phase / Module | Status | Key gaps |
|---|---|---|
| **P1** Avatar & Dashboard Truth | ✅ DONE | — |
| **P2** Frontend Perf Pass | ⚠️ PARTIAL | `useDeferredValue` absent; virtualization only on Orders |
| **P3** Model Tiers & Warmup | ✅ DONE | — |
| **P4** Companion Gateway | ⚠️ PARTIAL | 3 frontend components + `audit_logger.py` missing |
| **P5** Voice-First Teammate | ✅ DONE | — |
| **P6** Capability Adapters | ✅ DONE | — |
| **P7** Evolution Engine | ⚠️ PARTIAL | `trace_store.py` missing |
| **P8** UX Overhaul | ✅ DONE | — |
| **P9** Remote/Voice/PC Control | ⚠️ PARTIAL | ServiceControlPanel UI; Desktop Phase 2 orphaned; RPA proxy auth broken |
| **P9.5** Hybrid Rust | ❌ NOT STARTED | Intentionally deferred — profile data not yet gathered |
| **P10** CompanyOS | ⚠️ PARTIAL | 6 of 12 backend modules missing; memory graph + voice cmd absent |
| **M1** Browser Execution | ⚠️ PARTIAL | 3 files missing |
| **M2** Context DB | ⚠️ PARTIAL | 3 files missing |
| **M3** Forge Lifecycle | ⚠️ PARTIAL | 2 ui_quality files missing |
| **M4** Work Engine | ⚠️ PARTIAL | 6 files + marketplace_adapters/ missing |
| **M5** Content Factory | ⚠️ PARTIAL | `runtime/voice/` + `runtime/media/` entirely missing |
| **M6** FinanceOps | ⚠️ PARTIAL | Consolidated into one file; sub-modules absent |
| **M7** Business Swarm | ✅ DONE | — |
| **M8** Research Quality | ⚠️ PARTIAL | `source_collector.py` missing |
| **M9** Blacklight Defensive Skill OS | ❌ MISSING | Entire `security/skills/` + `security/tools/` absent |
| **M10** Harness Compat Layer | ❌ MISSING | No `runtime/harness/` directory |
| **M11** Reference Learning Library | ❌ MISSING | No `runtime/learning/reference_library/` |
| **M12** Model Arena | ❌ MISSING | No `runtime/core/arena/`; only orphan UI panel exists |

---

## P1 — Avatar & Dashboard Truth ✅ DONE

All evidence found:
- `backend/server.js` lines 592–604: `_realHwCache`, `_pollRealHardware()` polling every 5s
- `runtime/agents/problem-solver-ui/server.py` line 4303: `GET /api/system/resources` — nvidia-smi + psutil, returns `gpu_pct`, `gpu_temp`, `cpu_temp`, `vram_free_mb`, `disk_pct`
- `frontend/src/components/avatar/avatar-engine.js` + `frontend/public/avatar-engine.js` — both present
- `frontend/src/components/avatar/CognitiveEye.jsx` + `CognitiveEye.css` — present

**No gaps.**

---

## P2 — Frontend Performance Pass ⚠️ PARTIAL

### Done
- `useTransition` wired in `Dashboard.jsx:240` for page switches
- WS throttle: `system:status` coalesced to ~4Hz in `useWebSocket.js:387–405`; `nb:*` batch queue at line 157
- `useVirtualizer` imported and active in `OrdersPage.jsx:2,637`
- No bare `useAppStore()` calls found (selector hygiene clean)

### Gaps

| Gap | File | Plan reference |
|---|---|---|
| `useDeferredValue` never used | `frontend/src/` (none) | Plan: "useDeferredValue for heavy derived lists" |
| Virtualization only on OrdersPage | — | Plan: "event feed, agent grid, logs, orders" — only orders done |

**Priority:** Medium — visible 0.5s lag on heavy lists still possible.

---

## P4 — Companion Gateway ⚠️ PARTIAL

### Backend: 14/15 files present

Missing: `runtime/companion/audit_logger.py` (plan explicitly listed it alongside the 14 other files).

### Frontend: Under-built

Plan called for distinct components:
- `CompanionShell` — **not found** as its own file
- `AvatarStage` — **not found** as its own file  
- `CompanionChat` — **not found** as its own file
- `useCompanionSocket.js` — **not found**; only `frontend/src/store/companionStore.js` exists

The companion functionality routes through `ChatPanel.jsx` and `NexusOSDashboard.jsx` instead of dedicated components. This is workable architecturally but the dedicated surface the plan intended (companion-first shell layout) isn't present.

**Priority:** Medium for `audit_logger.py` (compliance gap — all companion actions should be logged). Low for frontend shape (functional, just not the planned decomposition).

---

## P7 — Evolution Engine ⚠️ PARTIAL

### Present: 11/12 files

```
candidate_registry.py  controller.py  distillation_adapter.py
failure_classifier.py  outcome_scorer.py  promotion_gate.py
reflection_engine.py   replay_harness.py  rollback_manager.py
scrub.py               trace_collector.py
```

### Missing

`trace_store.py` — plan: "JSONL → SQLite; `~/.ai-employee/evolution/`". The `trace_collector.py` appends traces but there is no durable SQLite-backed store module. Without it, traces survive only until process restart; replay and promotion gates can't query historical traces reliably.

**Priority:** High — evolution engine's value depends on persistent trace history.

---

## P9 — Remote / Voice / PC Control ⚠️ PARTIAL

### Done
- `backend/compute_fabric/` (index.js, persistence.js, remote_dispatch.js) — real GPU job lifecycle, artifact sync-back, heartbeat, cost caps all verified
- `COMPUTE_FABRIC_LIVE=0` gate correctly prevents accidental charges
- RunPod/VastAI listed in `compute_fabric/index.js:50–51` as `enabled: false` — intentional, awaiting provider credentials

### Gaps

**ServiceControlPanel UI not found.** Plan: "ServiceControlPanel + ComputeRouterStatus on Infrastructure page". Backend `/api/services` route exists (`backend/routes/services.js`) but no matching React panel found under `frontend/src/` — only `ComputeCenterPage.jsx` and `ComputerUseToggle.jsx` exist.

**Desktop Phase 2 orphaned.** `runtime/infra/rpa/desktop_worker.py` exists with `pyautogui` code and `FAILSAFE = True`, but:
- pyautogui not installed/unlinked on Linux
- No `desktop.*` capabilities registered in companion's `capability_registry.py`
- Plan explicitly noted this follow-up: "ungate+install pyautogui, add `desktop.*` caps"

**RPA proxy auth broken.** Plan noted: "Node `makeProxy('RPA')` doesn't forward a Python-valid token, so `/api/rpa/*` returns 500 at the boundary." This is an open follow-up from the Computer Use Mode commit.

**P9.5 (Hybrid Rust) — NOT STARTED — expected.** Only `src-tauri/src/lib.rs` (1428 lines) + `main.rs` exist — the Tauri shell. No native Rust hot-path modules (turbovec-style vector search, browser orchestration, audio processing) exist. Plan correctly says this requires profiling data from P2/P9 first. **This is not a gap — it's a deferred phase.**

---

## P10 — AI Company-Builder ⚠️ PARTIAL

### Backend: 8/14 planned modules present

| Present | Missing |
|---|---|
| `companyos.py` | `agent_team_orchestrator.py` |
| `company_planner.py` | `task_cycle_engine.py` |
| `company_store.py` | `build_integration.py` |
| `validation_engine.py` | `marketing_engine.py` |
| `founder_intake.py` | `support_engine.py` |
| `idea_refiner.py` | `metrics_engine.py` |
| `export_engine.py` | Memory graph linkage |
| — | Avatar/voice command wiring |

`companyos.py` has `run_company_cycle()` but it just calls `company_planner.run_cycle()` which in turn calls `AgentController.run_goal()` — there is no dedicated agent team orchestrator that maps CEO/CTO/Product/Marketing/Growth/Sales/Support/Finance/Security roles to specific agents.

`validation_engine.py` exists (120 lines) with `validate()` — scores market/competitor/demand — this is the core differentiator ("validate before building") and is present.

### Frontend: Partial

`CompanyBuilderPage.jsx` (607 lines) exists. Missing cockpit pages for: task cycle tracking, agent team status, marketing pipeline, metrics dashboard.

**Priority:** High — this is a "build last" phase per the plan sequence, but the missing orchestration layer (AgentTeamOrchestrator + TaskCycleEngine) is the operational core.

---

## Module 1 — Browser Execution Service ⚠️ PARTIAL

### Present: 7/10 files

```
browser_service.py  accessibility_snapshot.py  action_executor.py
capture.py  extract.py  tool_contracts.py  __init__.py
```

### Missing

| File | Purpose |
|---|---|
| `browser_session.py` | Per-task session lifecycle, profile isolation |
| `browser_sandbox.py` | Sandboxed per-task profiles (plan: "sandboxed per-task profiles") |
| `browser_events.py` | WS event emission: `browser:status`, `browser:action_started/finished/approval_required` |

Without `browser_events.py`, the browser subsystem can't emit real-time WS events to the frontend. Without `browser_sandbox.py`, the profile isolation guarantee (each task gets an isolated browser profile) is unimplemented.

**Priority:** High — `browser_events.py` is required for the companion gateway to stream browser activity.

---

## Module 2 — Context Database Layer ⚠️ PARTIAL

### Present: 6/9 files

```
context_tree.py  context_loader.py  recursive_retriever.py
session_compressor.py  context_permissions.py  __init__.py
```

### Missing

| File | Purpose |
|---|---|
| `context_node.py` | Individual node dataclass (path, content, type, trust_level, version) |
| `retrieval_trace.py` | The "trace always returned" requirement — debuggable retrieval path |
| `memory_writer.py` | Validated writes to context tree (the `write(path,content,validate)` interface) |

Without `context_node.py`, `context_tree.py` is likely using an ad-hoc dict structure. Without `retrieval_trace.py`, the "trace always returned" DoD is unmet. Without `memory_writer.py`, session data can't be durably written back.

**Priority:** Medium — retrieval reads work; write path and traceability are broken.

---

## Module 3 — Forge Lifecycle OS ⚠️ PARTIAL

### Lifecycle engines: COMPLETE

All 9 planned files present: `spec_engine.py`, `planning_engine.py`, `implementation_engine.py`, `test_engine.py`, `review_engine.py`, `simplify_engine.py`, `ship_engine.py`, `skill_selector.py`, `acceptance_criteria.py`.

### UI Quality: PARTIAL (3/5 files)

Present: `design_language_inferer.py`, `frontend_preflight.py`, `ui_auditor.py`

Missing:
| File | Purpose |
|---|---|
| `component_quality_checker.py` | Per-component quality scoring |
| `image_to_code_pipeline.py` | Visual-to-code generation (taste-skill ref: image→component) |

The UI anti-slop gate (`ui_auditor.py`) exists but the component-level checker and the image→code path are absent.

**Priority:** Low — the main lifecycle gates are in place.

---

## Module 4 — Work Acquisition Engine ⚠️ PARTIAL

### Present: 8/14 planned items

```
engine.py  deliverable_builder.py  feedback_store.py
fit_evaluator.py  opportunity_store.py  pricing_estimator.py
work_lifecycle.py  __init__.py
```

### Missing

| File | Purpose |
|---|---|
| `opportunity_ingestion.py` | Ingest from external sources (marketplaces, feeds) |
| `client_message_engine.py` | Approval-gated client communication (no autonomous messaging) |
| `submission_queue.py` | Stage → approve → submit two-gate pattern |
| `study_session_runner.py` | Offline learning loop feeding P7 distillation |
| `money_memory.py` | Persistent work/client memory across sessions |
| `marketplace_adapters/` | Directory of per-platform adapters (Upwork, Fiverr, etc.) |

`work_lifecycle.py` covers basic lifecycle but without `submission_queue.py` the two hard approval gates aren't enforced. Without `marketplace_adapters/`, there's no actual marketplace connectivity — the engine is self-contained with no inputs.

**Priority:** High for `submission_queue.py` (safety invariant: no autonomous submission). Medium for adapters.

---

## Module 5 — Content Factory + Creative Studio ⚠️ PARTIAL

### Content (`runtime/content/`): 5 files present

`content_factory.py`, `local_image_gen.py`, `media_models.py`, `muapi_client.py`, `publish_queue.py` — this is the image/content side.

### Voice module: ENTIRELY MISSING

`runtime/voice/` directory does not exist. Plan called for:
```
tts_router.py  voice_design.py  voice_clone_gate.py
streaming_tts.py  avatar_voice_controller.py
```
Voice functionality exists in `backend/services/voice/` and `runtime/agents/voice/` but the **companion-facing voice module** that routes TTS for content creation (not just the chat voice) and the consent-gated voice cloning path are absent.

### Media module: ENTIRELY MISSING

`runtime/media/` directory does not exist. Plan called for:
```
media_intake_service.py  source_permission_checker.py
transcript_extractor.py  subtitle_service.py
media_to_memory_pipeline.py
```
No media intake (yt-dlp integration, rights confirmation, license metadata) is implemented.

**Priority:** Medium — content factory core works for image/text; voice cloning gate and media ingestion are the missing safety-critical pieces.

---

## Module 6 — FinanceOps ⚠️ PARTIAL

`runtime/finance/financeops.py` (150 lines) — single consolidated file with `FinanceOps` class containing advisory methods. The plan listed 8 distinct modules (`business_model_builder`, `market_researcher`, `financial_model_drafter`, `pricing_analyzer`, `pitch_memo_builder`, `revenue_forecaster`, `human_review_gate`, `finance_agent_registry`) which are consolidated here.

The `human_review_gate` is referenced in comments but not a separately enforced module. `requires_human_signoff` flag exists in the response schema.

**Priority:** Low — advisory-only, consolidated is acceptable. The `human_review_gate` should be a hard enforcement module, not a flag.

---

## Module 7 — Business Swarm Layer ✅ DONE

All 10 planned files present: `agent_contracts.py`, `assignment_engine.py`, `capability_profiles.py`, `dependency_manager.py`, `parallel_executor.py`, `registry.py`, `result_aggregator.py`, `swarm.py`, `task_decomposer.py`, `__init__.py`.

---

## Module 8 — Research Quality Engine ⚠️ PARTIAL

### Present: 8/9 files

```
citation_anchor.py  claim_auditor.py  integrity_gate.py
material_passport.py  report_builder.py  research_planner.py
reviewer_panel.py  source_verifier.py
```

### Missing

`source_collector.py` — plan: collects sources from search results and prepares them for `source_verifier.py`. Without it, the pipeline has verifier logic but no structured intake of raw sources.

Total: 814 lines across 8 files — these are stub-level implementations (avg ~100 lines each). Functional APIs but light on actual verification logic depth.

**Priority:** Low — `source_collector.py` is the missing link in the pipeline.

---

## Module 9 — Blacklight Defensive Skill OS ❌ MISSING

Only `runtime/security/policy.py` exists under `runtime/security/`.

### Entirely absent:
- `runtime/security/skills/` — entire directory (planned: `security_skill_registry`, `skill_frontmatter_index`, `framework_mapper`, `security_skill_loader`, `defensive_workflow_runner`, `verification_engine`, `report_templates`, `scope_gate`)
- `runtime/security/tools/` — entire directory (planned: `security_tool_registry`, `tool_scope_validator`, `process_manager`, `risk_card_generator`, `authorization_gate`)

The existing `backend/routes/security-ops.js` (624 lines) has `blacklight` routes, but these route to `blacklight_tools.js` — a Node-side tool runner, not the Python defensive skill OS with MITRE/NIST/ATLAS/D3FEND framework tags and scope-gated authorization.

**Priority:** Medium — security monitoring exists; the structured defensive skill OS (framework mappings, progressive disclosure, active-scan gating) does not.

---

## Module 10 — Harness Compatibility Layer ❌ MISSING

`runtime/harness/` directory does not exist.

No exporter modules for Claude Code / Codex / Cursor / OpenCode / Gemini / Copilot exist. No `rules_compiler`, `hook_manager`, or `mcp_config_generator`.

`tools/ai_employee_cli/` does not exist either.

**Priority:** Low — packaging concern; no active feature is blocked. Required before public release or multi-harness deployments.

---

## Module 11 — Reference Learning Library ❌ MISSING

`runtime/learning/reference_library/` does not exist. Various `learning_*.py` files live in `runtime/core/` (learning_engine, learning_orchestrator, learning_ladder_builder, agent_learning_profile) — these are the agent self-improvement systems, not the reference architecture library (build-your-own-x patterns for Forge).

**Priority:** Low — context-only module; feeds Forge skill OS enrichment but not a runtime dependency.

---

## Module 12 — Model Arena Mode ❌ MISSING

`runtime/core/arena/` directory does not exist.

Only `runtime/ui/agent_arena/arena_panel.py` exists — an orphaned UI panel with no backend.

Planned: `model_race.py`, `output_scorer.py`, `routing_feedback.py`, `sampling_autotune.py`, `response_normalizer.py`, `model_benchmark_store.py`.

**Priority:** Medium — feeds P7 evolution engine with routing preference updates; also the quality data for `model_lanes.py` dynamic routing improvement.

---

## Cross-cutting gaps not in a single phase

### 1. RPA proxy auth (`/api/rpa/*` returns 500)
`backend/routes/security-ops.js` mounts the RPA router; the Node `makeProxy('RPA')` call doesn't forward a Python-valid JWT. Noted as an open follow-up in the Computer Use Mode commit. The companion path bypasses this, but standalone RPA HTTP is broken.

### 2. `useDeferredValue` (P2)
Zero uses anywhere in `frontend/src/`. Heavy derived lists (agent grid, research panel) will block the render thread on large datasets.

### 3. Voice module split
The plan creates `runtime/voice/` as the content-creation TTS layer distinct from `backend/services/voice/` (the chat voice). This split is not done — all voice lives in `backend/services/voice/`. Module 5's `avatar_voice_controller.py` and `voice_clone_gate.py` (with consent token) are missing.

### 4. Media pipeline absent
No `runtime/media/` means there is no rights-checked media ingestion, no transcript extraction, no subtitle generation, and no media→memory pipeline for content creation workflows.

---

## Prioritized build order (what to do next)

Based on dependencies and risk level:

### Tier 1 — Fix broken / safety gaps (do first)

1. `runtime/evolution/trace_store.py` — evolution engine can't retain history without it
2. `runtime/companion/audit_logger.py` — compliance; companion actions unlogged
3. `runtime/tools/browser/browser_events.py` — companion can't stream browser activity
4. `runtime/money/work_engine/submission_queue.py` — safety invariant; blocks autonomous submission
5. RPA proxy auth fix — `/api/rpa/*` dead at the Node→Python boundary

### Tier 2 — Complete partial modules

6. `runtime/tools/browser/browser_session.py` + `browser_sandbox.py` — profile isolation
7. `runtime/memory/context_db/context_node.py` + `retrieval_trace.py` + `memory_writer.py`
8. `runtime/forge/ui_quality/component_quality_checker.py` + `image_to_code_pipeline.py`
9. `runtime/research/quality/source_collector.py`
10. `runtime/finance/` — extract `human_review_gate.py` as hard enforcement module

### Tier 3 — Complete P10 CompanyOS backend

11. `runtime/companyos/agent_team_orchestrator.py` (maps CEO/CTO/etc → existing agents)
12. `runtime/companyos/task_cycle_engine.py` (recurring loops + approval checkpoints)
13. `runtime/companyos/build_integration.py` (Forge sandbox wiring)
14. `runtime/companyos/marketing_engine.py`, `support_engine.py`, `metrics_engine.py`
15. Memory graph linkage in CompanyOS
16. Frontend: TaskCycle, AgentTeam, Marketing, Metrics cockpit pages

### Tier 4 — Build missing modules (M9, M10, M11, M12)

17. **M12 Model Arena** (`runtime/core/arena/`) — 6 files; feeds evolution routing quality
18. **M9 Blacklight Skill OS** (`runtime/security/skills/` + `security/tools/`) — 16 files
19. **M5 voice/media** (`runtime/voice/` 5 files + `runtime/media/` 5 files)
20. **M4 Work Engine completion** (6 missing files + `marketplace_adapters/`)
21. **M10 Harness** (`runtime/harness/` 10 files + CLI) — pre-release packaging
22. **M11 Reference Library** (`runtime/learning/reference_library/` 6 files)

### Tier 5 — P2 perf + P9.5 Rust (evidence-driven)

23. `useDeferredValue` on heavy derived lists (agent grid, research panel)
24. Virtualize event feed + logs (extend `@tanstack/react-virtual` pattern from OrdersPage)
25. P9.5: gather profiling data first (P2 + P9 instrumentation), then decide which paths to rewrite

---

## Total gap count

| Category | Count |
|---|---|
| Entirely missing modules | 4 (M9, M10, M11, M12) |
| Partially built modules | 9 (P2, P4, P7, P9, P10, M1, M2, M3, M4, M5, M6, M8) |
| Missing individual files across partial modules | ~25 |
| Cross-cutting issues | 5 |
| Intentionally deferred (P9.5) | 1 |
| Fully done | 7 (P1, P3, P5, P6, P8, M7, P9-core) |

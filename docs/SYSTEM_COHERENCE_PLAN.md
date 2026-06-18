# System Coherence Plan — Make Every Built System Work As One

**Date:** 2026-06-18 · **Author:** Pulse (for Lars) · **Status:** PROPOSAL — awaiting approval before execution
**North star (Lars):** architectural coherence first — enforce the Orchestrator → Skills → Tools spine; nothing orphaned.
**Money anchor (Lars):** website-sales demos = the first revenue pipeline made fully real (clickable → working → earning).
**Method:** doc first → approve → execute phase-by-phase, one PR per phase, parallel sub-agents to map, I execute.

Evidence base: 5 parallel read-only subsystem maps (execution spine · agents/skills/tools · revenue · frontend reachability · backend/infra). Every claim below is cited to `file:line` in those maps; spot-verify before each phase.

---

## 1. The one-sentence truth

**The system is broad and ~mostly real at the surface (634 backend routes ~94% authed, ~30 of ~33 dashboard pages functional, a working website-sales loop), but it is NOT one system — it is three parallel execution brains and three disconnected capability catalogs sitting on a split-brain state layer.** The "messiness" is not stub-rot; it is *incoherent wiring underneath a solid surface*.

The four structural fractures:
1. **Three orchestrators, not one** — `unified_pipeline`+`AgentController`, the Node `turn-runner` ladder, and the `companion` runtime each run their own intent-classify → model-select → execute, sharing no code. The documented pipeline is *bypassed on the hot chat path on both the Node and Python sides.*
2. **Three disconnected catalogs** — only **3 of ~125** agents touch the skills/tools registry; **565 of 570** skills are prompt templates with no tools; agents run as standalone polling daemons; the Node agent layer **fabricates** task completions on timers.
3. **Split-brain state** — tasks/artifacts/research write to repo-local `./state`, ledgers/telemetry to `~/.ai-employee/state`; the canonical store writes JSON with **no working lock** (silent last-writer-wins). Tenancy is enforced at the JWT boundary but **not** at storage.
4. **Revenue is a side-system** — the website-sales loop works but never touches the spine, and is blocked from earning by `localhost` demo URLs, 3 missing endpoints, and no real payment capture.

Fixing coherence = collapse 3 brains → 1 spine, 3 catalogs → 1 chain, 2 state trees → 1 store, and put revenue *on* the spine.

---

## 2. What the system CAN do today (capability inventory)

### Surface that genuinely works
| Layer | Working capabilities (evidence) |
|---|---|
| **Dashboard** | ~30 of ~33 sidebar pages functional end-to-end: Nexus, Cognition, Agents, Memory, Economy, Orders/Sales, Company Builder, Tasks, Workflows, System Health, Ascend Forge, Neural Graph, Quantum Brain, Knowledge, Research, Prompt Inspector, Security/Recon/Audit/Approvals/Proof, Setup, Integrations, **Models (A7)**, Model Fabric, Compute, Settings. WS telemetry broadly wired (`useWebSocket.js:226-1014`); localhost-operator auth works. |
| **Backend API** | 634 registered routes, ~94% require auth; Forge alone = 168 endpoints; 15 `infra/*` routers real (sandbox runs RBAC-gated commands; healing/rag proxy to Python with permission gates). |
| **Model orchestration** | A0–A7 landed (PR #273): quant-aware inference, KV-aware VRAM budget, one-heavy-at-a-time lifecycle, hard PC-control gate (A5), Models page observability. `execution_reasoning → gemma3:4b-it-qat`. |
| **Website-sales loop** | ~80% wired + persisted to SQLite (`audit.db` orders table): find leads (real DuckDuckGo) → create → research → generate demo → quality gate → HITL approve → pitch (local Ollama) → mark sent/akkoord. |
| **Tools** | ~10 of 14 real: web_search, read/write/create_file, llm_infer, embed_text, get_memory, call_api, browser_fetch, media_generate (local image gen, offline-first). |
| **Content/data money_mode** | content_publish_track generates real LLM markdown artifacts; data_scrape_filter_store really fetches/dedupes/stores to knowledge_store. |
| **Observability** | metrics_collector thread (CPU/mem/task/api/error snapshots, 3600 ring), event_stream → `observability_events.db` (24MB live), audit → `audit.db` (WAL). |
| **Auto-research loop** | context-sufficiency scoring → adaptive web research → 3-layer persist; WS events + ContextCheckModal wired. |

### Built but NOT reachable / NOT real (the orphan layer)
- **DeepResearch page** — fully built in Python (`server.py:13745-13856`) but **dead**: Node `research.js` doesn't proxy `/deep*` → 404.
- **14 page components** built, never mounted: Doctor, Evolution, Hermes, Fairness, LearningLadder, Training, Voice, History, NeuralBrain, AIControl, ControlCenter, Onboarding, System, Blacklight.
- **Large backed subsystems, no front door**: Work Acquisition Engine (`/api/work/*`), Wallet, Channels, Cluster, Users/Roles/Permissions, the `infra/*` Phase 2–4 routers (events, sandbox, secrets, planning, economics, governance, telemetry, rpa, healing, marketplace, deployment, simulation, cognitive).
- **Node agent activity is simulated** — `backend/agents/index.js:224-289` completes tasks on `finishAt` timers and emits `task:completed` without running any agent.
- **565/570 skills** are prompt templates; the multi-page demo composer (`demo_blocks/composer.py`) is fully built but **unwired** (active generator emits a one-pager).

---

## 3. Consolidated gaps (ranked, grouped by theme)

> P0 = breaks one-system coherence or earning · P1 = major incoherence/risk · P2 = hygiene/scale · P3 = cleanup.

### Theme A — Execution spine fragmentation
| # | Gap | Evidence | Sev |
|---|---|---|---|
| A1 | `unified_pipeline` bypassed: Python `post_chat` returns from `real_execution_engine` / `_direct_conversation_reply` before the pipeline; Node `turn-runner` reaches it only as rung 3 of 5 | `server.py:5897-5965`, `turn-runner.js:345-449` | P0 |
| A2 | Companion runtime is a complete 2nd orchestrator sharing zero code with pipeline/AgentController | `conversation_runtime.py:83`, `execution_broker.py:112-280` | P0 |
| A3 | Three independent intent classifiers + three "process input" normalizers → same sentence routes differently per entrypoint | `engine/api.py:81`, `unified_pipeline.py:388`, `conversation_runtime.py:128` | P1 |
| A4 | Orchestrator→tool layering inconsistent: AgentController routes via SkillCatalog (clean), but ExecutionBroker calls subsystems directly and `classify_decision` hardwires intent→agent in a static dict | `agent_controller.py:256,583`, `execution_broker.py:112-143`, `unified_pipeline.py:352` | P1 |
| A5 | Memory retrieval duplicated in Node and Python | `turn-runner.js:313` + `unified_pipeline.py:188-263` | P2 |

### Theme B — Agents / Skills / Tools disconnection
| # | Gap | Evidence | Sev |
|---|---|---|---|
| B1 | Only 3 of ~125 agents use skills/tools registry; rest are standalone polling daemons with their own LLM calls; Executor never invokes an agent | `lead_generator.py:554`, `executor.py:104` | P0 |
| B2 | 565/570 skills have no impl + no tool linkage; every dispatch collapses to "ask LLM as role X"; library `system_prompt`/`execution_steps` are dead data | `catalog.py:136`, `agent_controller.py:617`, `skills_library.json` (0 tool fields) | P0 |
| B3 | Node `backend/agents/index.js` fabricates agent activity (timer-based `task:completed`, never runs `run.sh`/Python) | `index.js:224-289,357` | P0 |
| B4 | 4 registered tools are stubs (`update_db`, `send_email` HITL-blocked) → skills needing them can't complete | `registry.py:191,193` | P2 |
| B5 | 12 orphan agent dirs + ~50 agent `.py` without BaseAgent → no uniform dispatch contract | agent dir scan | P3 |

### Theme C — State & data integrity (the bedrock)
| # | Gap | Evidence | Sev |
|---|---|---|---|
| C1 | State-dir split-brain: tasks/artifacts/research → repo-local `./state`; ledgers/telemetry → `~/.ai-employee/state`; Node mixes both | `state_store.py:30`, `artifact_manager.py:31`, `cost_ledger.py:61`, `dashboard-api.js:290` | P0 |
| C2 | Canonical StateStore writes JSON with no lock (`raw write_text`); FileLock is `LOCK_NB`+swallow, `timeout` param unused → silent last-writer-wins | `state_store.py:52`, `file_lock.py:33,42` | P0 |
| C3 | Tenancy enforced at JWT boundary, not storage: 3 competing models, only 1/6 locked writes pass tenant_id; `get_tenant_state_dir` auto-provisions unknown tenants (fail-open) | `tenancy.py:104-108,192`, `file_lock.py:74-97`, `state_store.py:110` | P1 |
| C4 | JSON-file state + in-process bus + single-process metrics = hard single-node ceiling; Postgres path exists but JSON is the live fallback | `state_store.py` `_use_pg` | P1 |

### Theme D — Revenue (website-sales anchor)
| # | Gap | Evidence | Sev |
|---|---|---|---|
| D1 | Demo links are `localhost` — customer can't open the demo; `BASE_URL` read but never set | `pitch.py:32,99-104` | P0 |
| D2 | 3 SalesPage endpoints 404 (`/update`, `/photo`, `/stuur-link`) → edit/photo/share break | `SalesPage.jsx:181,207,351` vs `orders.js` (absent) | P0 |
| D3 | PayPal link is placeholder (`paypal.me/jouwlink`); no verified payment capture (any typed ref trusted) | `pitch.py:28,212` | P1 |
| D4 | Hosting needs manual `NETLIFY_API_TOKEN`; deploys single file only (folder demos can't deploy) | `hosting.py:33,60-66` | P2 |
| D5 | Orders flow is a side-system — no skill/AgentController/pipeline reference; multi-page composer dead-wired | grep (empty), `demo_blocks/composer.py` | P1 |
| D6 | outreach_response_conversion never sends (draft only); content_publish never publishes to a channel | `money_mode.py:658-895` | P2 |

### Theme E — Reachability & orphans
| # | Gap | Evidence | Sev |
|---|---|---|---|
| E1 | DeepResearch page dead — Node `research.js` lacks `/deep*` proxy | `research.js` (only `/discover`,`/execute`) | P0 |
| E2 | 14 built page components never mounted; backends mostly exist | `Dashboard.jsx` PAGES registry | P1 |
| E3 | Major backed subsystems with no front door (Work Engine, Wallet, Users/Roles, infra/* Phase 2–4) | `index.js` registry | P1 |
| E4 | Dead button `/api/intelligence/trigger-action` (no backend route) | `IntelligencePage.jsx:156` | P2 |

### Theme F — Security & observability hygiene
| # | Gap | Evidence | Sev |
|---|---|---|---|
| F1 | Public-by-default sensitive routes (`/api/wallet/status`, `/api/autonomy/policy`, `/api/sessions`, `/api/integrations*`); `/metrics` open unless `METRICS_TOKEN` | `fork-integrations.js`, `server.js:4025` | P2 |
| F2 | 634-entry route registry `auth:` flags are docs, not enforced vs actual mounts → silent-public drift | `index.js` vs `server.js:516-590` | P2 |
| F3 | Observability single-process/in-memory, lost on restart, no per-tenant dimension | `metrics_collector.py:85` | P3 |

---

## 4. The coherence target (what "one system" means)

```
ONE ENTRY (chat · tasks · companion · money · agent)
        │
        ▼
  unified_pipeline  ── single intent service ──┐  (one classify, one memory, STRICT everywhere)
        │                                       │
        ▼                                       │
  AgentController (Planner→Executor→Validator)  │
        │                                       │
        ▼                                       │
  SkillCatalog ──► Skills (real tools[]+steps) ─┘
        │
        ▼
  ToolRegistry ──► Tools (atomic, schema'd, no business logic)
        │
        ▼
  ONE state store (resolve_state_dir → locked, tenant-aware, Postgres-default)
        │
        ▼
  Real outcomes (demo published, payment captured, content posted) — surfaced in ONE dashboard
```
Rules made true: one spine (no bypass), agents dispatch *through* skills (no bespoke LLM calls), skills *compose tools* (not prompt templates), one state tree (no split-brain, no silent clobber), tenancy at storage, every built capability either reachable or explicitly archived, no fabricated telemetry.

---

## 5. Phased roadmap (one PR per phase, each with proof)

Ordered for **coherence-first** with the **money anchor** woven in. Each phase is independently shippable and ends with a verifiable acceptance test. Estimates are relative size, not time.

### Phase C0 — Foundation: one state tree, real locking  ⟶ *unblocks everything* (P0: C1,C2)
- One `resolve_state_dir()` (env `STATE_DIR` → `AI_HOME/state`) imported by every Python module + mirrored in Node; ban `Path(__file__).parents[2]/state` and `__dirname/../../state`. One-time migration of stray repo-local state.
- Route all `StateStore._save_json`/`_load_json` through `write_json_safe`/`read_json_safe`; make `FileLock` **blocking** using its existing-but-unused `timeout` (retry loop), stop swallowing lock failures.
- **Proof:** concurrent-write test shows no lost update; `git status` never shows stray `state/*`; one state tree on disk. Size: M.

### Phase C1 — One execution spine (P0: A1,A2 · P1: A3,A4)
- Invert Python `post_chat`: `real_execution_engine` + direct-reply become Phase-6 strategies *inside* `process_user_input`, not pre-returns. Make Node `turn-runner` call the pipeline first, fallback ladder after.
- Make the companion runtime's execution mode **delegate to `AgentController.run_goal()`** instead of its own `ExecutionBroker` dispatch.
- Collapse the 3 intent classifiers + static `_INTENT_AGENT_PROFILES` onto **one shared intent+skill-registry service**.
- **Proof:** identical input classifies identically across chat/tasks/companion; `STRICT_PIPELINE=1` surfaces failures on all entrypoints; single call-graph diagram. Size: L.

### Phase C2 — One agent/skill/tool chain (P0: B1,B2,B3)
- `BaseAgent.execute()` dispatches through `SkillCatalog`/`ToolRegistry` (stop reimplementing LLM calls). Migrate agents off bespoke poll-loops incrementally (start with the revenue + lead agents).
- Give library skills a real `tools[]` + `execution_steps` executable contract + an interpreter in `_emit_action` that **uses** the library `system_prompt`/`execution_steps` and runs the tool steps. Convert the top N revenue-relevant skills first.
- Replace Node `index.js` simulation with **real** Python agent execution — no fabricated `task:completed`.
- **Proof:** a chosen skill runs its declared tool chain (not a generic prompt); dashboard agent activity maps 1:1 to real runs; count of executable skills ≫ 5. Size: L.

### Phase C3 — Website-sales earns, on the spine (the money anchor) (P0: D1,D2 · P1: D3,D5)
- **Quick wins (can ship immediately, independent of C0–C2):** add the 3 missing routes (`/update`, `/photo`, `/stuur-link`); set `BASE_URL` via tunnel **or** deploy-to-Netlify-before-pitch so demo links open; set `PAYPAL_LINK` + `NETLIFY_API_TOKEN` in `.env`.
- **Coherence:** expose the orders loop as a real **Skill** (`website_sales`) composed of tools (finder, research, demo, pitch, deploy) so it runs *on the spine*, not as a side-system; wire the multi-page composer or formally accept the one-pager.
- **Earning (stretch):** swap PayPal.me for a Stripe Payment Link + `/api/orders/webhook` that flips `betaald` on real `checkout.session.completed`.
- **Proof:** end-to-end — create → customer opens a public demo → pays → status auto-flips to `betaald`. **First euro path is real.** Size: M (quick wins S, Stripe M).

### Phase C4 — Reachability: close the front doors (P0: E1 · P1: E2,E3 · P2: E4)
- Add `router.all('/deep*', proxy)` in `research.js` (unblocks DeepResearch — 1-line class).
- Mount/route the 14 orphaned pages + sidebar entries, OR prune the truly dead ones (decide per page). Surface orphaned backends (Work Engine, Wallet, Users/Roles) behind nav or explicitly defer.
- Back or remove dead buttons (`/api/intelligence/trigger-action`).
- **Proof:** every sidebar page functional; an inventory shows each built capability is reachable or archived (no silent orphans). Size: M.

### Phase C5 — Tenancy, security & scale hardening (P1: C3,C4 · P2: F1,F2 · P3: F3)
- Collapse the 3 tenancy models into one **storage-enforced** model (per-tenant path), fail closed on unknown tenant. Make StateStore tenant-path-aware.
- Promote the Postgres path to default for tasks/knowledge/deals; plan bus → real broker (design only this phase).
- Require auth on wallet/session/autonomy reads; default `/metrics` to localhost. Boot-time assertion that every registry entry maps to a mounted guard. Add `tenant_id` metric label + persist counters.
- **Proof:** cross-tenant isolation test passes at the data layer; no public sensitive routes; registry==mounts assertion green. Size: L.

**Suggested merge order:** C0 → C1 → C2 → C3 → C4 → C5. C3's *quick wins* may be pulled forward to start earning while C1/C2 land.

---

## 6. What I will NOT do without your explicit go
- Anything in this doc (approach = doc first, approve, then execute).
- Cost/infra commitments: Stripe account, public tunnel/hosting domain, rented GPU (A8), TurboQuant fork, Postgres provisioning.
- Deleting orphaned code (the 14 pages, dead skills) — I'll propose keep-vs-prune per item, you decide.

## 7. Open decisions for you
1. **Start order:** strict C0→C5, or pull C3 quick-wins forward to earn while coherence lands?
2. **Public demo hosting:** Netlify (token) vs a tunnel (`cloudflared`) vs a real domain — which?
3. **Payment:** stay manual PayPal.me short-term, or go straight to Stripe for verified/autonomous capture?
4. **Orphan policy:** default to *mount & surface* the 14 pages + backed subsystems, or *prune* aggressively?
5. **Scope of C2:** convert all 570 skills to executable, or only the high-value set (revenue/lead/content) first?

---
*Generated from 5 evidence-cited subsystem maps. Cross-check `file:line` before each phase — maps are point-in-time. PR #273 (model A4/A6/A7) is the template for the per-phase, proof-backed delivery this plan follows.*

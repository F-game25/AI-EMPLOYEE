# AI Employee — Master Plan
**Status: EXECUTING**
**Last updated: 2026-06-05**

> One system. All your compute. Generating money 24/7 — on desktop, laptop, or a cluster of both — without ever crashing or slowing down your computer.

---

## Hardware

| Machine | GPU | VRAM | RAM | CPU | Role |
|---|---|---|---|---|---|
| Desktop | RTX 2070 Super | 8 GB | 15.6 GB | Ryzen 5 3600 12-core | Primary |
| Laptop | RTX 3060 Ti | 8 GB | ~16 GB | Ryzen 7 8-core | Worker |

Both detected automatically by `ResourceManager`. No manual config needed.

---

## Execution Order & Status

| # | Phase | Status |
|---|---|---|
| 0 | Resource safety — auto-detect hardware, OS reserve budgets | ✓ DONE |
| 1 | Smart model selection + CPU/RAM offload for every Ollama call | ✓ DONE |
| 2 | Agent engine — ReAct loop, tool registry, SwarmController | ✓ DONE |
| 3 | Cluster infra — UDP discovery, TOTP 2FA pairing, Cluster Settings tab | ✓ DONE |
| 4 | **Voice fix** — VRAM threshold corrected, auto STT/TTS wired to ResourceManager | ✓ DONE |
| 5 | **Model warming** — llama3.2 + nomic-embed-text always hot, per-step model routing | ✓ DONE |
| 6 | **Compute Planner** — assess needs before every task, OpenRouter overflow, remote GPU proposal | ✓ DONE |
| 7 | **Cluster ↔ Swarm** — SwarmController delegates heavy subtasks to worker node | ✓ DONE |
| 8 | **UI: Compute plan badge in AscendForge** — model + strategy shown per run | ✓ DONE |
| 9 | Revenue automation — idle compute scheduler, auto-publish, revenue tracker | → NEXT |

---

## PHASE 0 — Resource Safety ✓ DONE

- `runtime/engine/compute/resource_manager.py` — auto-detects GPU/VRAM/RAM/CPU
- Budget ceilings: 85% VRAM, 70% RAM, 75% CPU (60% on laptops/low-RAM machines)
- OS floor: always reserves ≥ 2 GB RAM + 512 MB VRAM + 25% CPU
- Refreshes every 30s. Exposed at `GET /system/resources`.

---

## PHASE 1 — Smart Model Selection ✓ DONE

- `turbo_quant._MODEL_CATALOGUE` uses installed models: llama3.2, gemma3, qwen2.5:7b, qwen2.5-coder:14b, llava, nomic-embed-text
- `_build_ollama_options()` computes `num_gpu`, `num_thread`, `num_batch`, `low_vram` per model call
- `ResourceManager.select_llm_stack()` + `select_voice_models()` pick per-machine model stack
- RAM pressure adjustment: if free RAM < 3 GB → push more layers to GPU

| Task | Desktop | Laptop | Always available |
|---|---|---|---|
| Fast routing | llama3.2 (2GB) | llama3.2 | hot |
| General | gemma3 (3.3GB) | gemma3 | hot |
| Reasoning | qwen2.5:7b (4.7GB) | qwen2.5:7b | on demand |
| Code | qwen2.5-coder:14b (9GB, offload) | qwen2.5-coder:7b | on demand |
| Vision | llava (4.7GB) | llava | on demand |
| Embed | nomic-embed-text (400MB) | same | hot |
| STT | whisper_base | whisper_base | hot |
| TTS | voice_lite / kokoro | voice_lite | hot |
| Cloud overflow | meta-llama/llama-3.1-8b:free (OpenRouter) | same | free |

---

## PHASE 2 — Agent Engine ✓ DONE

- `runtime/engine/agent/agent_loop.py` — ReActAgent: Reason→Act→Observe, 15 steps
- `runtime/tools/implementations/` — shell_exec, code_exec, file_ops, web_fetch
- `runtime/agents/react_coder/`, `react_researcher/`, `react_planner/`
- `runtime/core/swarm/swarm_controller.py` — parallel multi-agent decomposition
- `runtime/core/tool_approval_gate.py` — HITL blocking for risk-2+ tools
- `/swarm/run`, `/swarm/stream/:id`, `/react/run` FastAPI endpoints
- AscendForge Full Auto → SwarmController

---

## PHASE 3 — Cluster Infrastructure ✓ DONE

- `runtime/engine/compute/cluster_node.py` — UDP multicast LAN discovery, pure-stdlib TOTP 2FA
- Pairing flow: PRIMARY generates code+secret → user enters on BOTH machines → bidirectional 2FA
- Worker endpoints: `/cluster/infer`, `/cluster/agent_run`, all 2FA-protected
- `backend/routes/dashboard-api.js` — cluster proxy routes
- `frontend/.../settings/ClusterTab.jsx` — full UI: node cards, resource gauges, pairing wizard
- `SettingsPage.jsx` → CLUSTER tab wired in

**Setup:**
```bash
# ~/.ai-employee/.env on BOTH machines:
AI_CLUSTER_TOKEN=your-secret-phrase   # same on both
AI_NODE_ROLE=primary                  # desktop
AI_NODE_ROLE=worker                   # laptop
```
Then Settings → CLUSTER tab to complete 2FA pairing.

---

## PHASE 4 — Voice Fix ✓ DONE

- `FISH_MIN_VRAM_MIB` corrected: 24 GB → 3 GB (was blocking all consumer GPUs)
- `ResourceManager.select_voice_models()` returns whisper_base/voice_lite for 8GB VRAM cards

---

## PHASE 5 — Model Warming & Per-Step Routing ✓ DONE

**Goal:** Hot models are always ready. Each ReAct step uses the cheapest model that can do the job.

**Tasks:**
- [ ] `runtime/engine/inference/llm.py` — `warm_core_models()`: send `keep_alive: -1` to llama3.2 + nomic-embed-text at startup
- [ ] Call `warm_core_models()` from server.py Wave B startup (alongside ResourceManager + ClusterNode)
- [ ] ReActAgent `_reason()` — pick model by step type: tool-call step → llama3.2, analysis step → gemma3, code step → qwen2.5-coder
- [ ] `SwarmController._run_subtask()` — pass `model_hint` from ComputePlanner (Phase 6) into ReActAgent

---

## PHASE 6 — Compute Planner ✓ DONE

**Goal:** Before every task, assess what compute is needed. Always cheapest first. User approves spend.

**Decision flow:**
```
Task arrives → assess(goal, context_len, complexity)
  → local_tiny (llama3.2)         if simple Q&A, routing
  → local_reasoning (qwen2.5:7b)  if research, multi-step
  → local_coder (qwen2.5-coder)   if code generation
  → openrouter_free               if exceeds local VRAM budget
  → rent_gpu (HITL approval)      if needs >8GB sustained or very long task
```

**Files to build:**
- [ ] `runtime/engine/compute/compute_planner.py` — `ComputePlan` dataclass, `assess_compute_needs(goal, context_len) → ComputePlan`
- [ ] `runtime/engine/compute/remote_provisioner.py` — Vast.ai/RunPod API: provision, poll, terminate
- [ ] Extend HITL gate with `rent_compute` action type + approval card in AscendForge
- [ ] Wire ComputePlanner into `AgentController.run_goal()` before task dispatch

---

## PHASE 7 — Cluster ↔ Swarm Integration ✓ DONE

**Goal:** When a subtask needs more VRAM than local has free → auto-delegate to worker node.

**Tasks:**
- [ ] `ClusterNode.best_worker(vram_needed_mb)` — returns peer with most free VRAM above threshold
- [ ] `SwarmController._run_subtask()` — if `vram_needed > local_free * 0.8` → dispatch to worker via `POST /cluster/agent_run`
- [ ] Worker pre-warms model before subtask arrives (`POST /cluster/warm`)
- [ ] Bandwidth check: skip remote dispatch if context > 50KB and peer is on WiFi (add `link_speed_mbps` to beacon)

---

## PHASE 8 — UI: Compute + Model Panels (NEXT)

**Goal:** See every resource, every model, every cluster node — live.

**Tasks:**
- [ ] SystemSetupCenter → Compute tab: VRAM/RAM/CPU live gauges, models currently loaded
- [ ] Model manager panel: installed models, VRAM each uses, load/evict/pull buttons
- [ ] Cluster node cards already in CLUSTER settings tab — add live task count + routing indicator
- [ ] AscendForge sidebar: show ComputePlan (model chosen, cost estimate) before task runs
- [ ] Revenue tracker widget: $ generated this session / this week (Phase 9 prerequisite)

---

## PHASE 9 — Revenue Automation (PLANNED)

**Goal:** Generate money while idle.

**Revenue streams:**
| Stream | Agents | Revenue type |
|---|---|---|
| Content creation | content-generator, blog-writer, social-caption | Freelance / SaaS |
| Lead generation | lead-hunter-elite, outreach, email sequences | B2B pipeline |
| Code/SaaS | react_coder + react_planner | Product revenue |
| Research reports | react_researcher + report-generator | Consulting |

**Tasks:**
- [ ] Idle compute detector: if no user task for >5min → start revenue task from queue
- [ ] Revenue task queue: priority-ordered list of income-generating tasks
- [ ] Output delivery: auto-publish content, send outreach (HITL approval per send)
- [ ] Revenue dashboard widget: $ generated per agent, tasks completed, ROI vs compute cost

---

## Security (Non-negotiable)

- Cluster: shared token + TOTP 2FA. LAN-only by default.
- Remote compute: encrypted in transit. No plaintext model inputs to third parties.
- User approval before: spending money, sending to external parties, renting compute.
- Resource budgets: can NEVER take OS-critical resources (2GB RAM floor, 512MB VRAM floor).
- Cluster token: never logged, never in code.

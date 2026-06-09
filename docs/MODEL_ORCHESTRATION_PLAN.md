# Model Orchestration & Performance — The Big Plan

**Target hardware:** RTX 2070 Super (8 GB VRAM), 15 GB RAM, 12-core CPU
**Goal:** A flawlessly operating system that runs a decent model + smaller models on a normal PC — loading the right model per task, offloading to CPU/RAM where needed, handing context between models, and falling back to OpenRouter free tier when local resources are exhausted.

---

## Phase 0 — Self-assessing compute needs & remote compute provisioning

**New requirement (added 2026-06-05):** When a task is created with a goal, the system must:

1. **Self-assess what compute is needed** — before picking a model, evaluate the task complexity, required context length, expected output size, and time constraints. Choose the cheapest local model that can produce quality output. If no local model is sufficient (e.g. task needs 70B reasoning, context > 32K, or multimodal with high accuracy), escalate.

2. **Suggest renting remote compute** — if local resources are insufficient and OpenRouter free tier is too slow/unavailable, emit a structured suggestion to the user: `{ "action": "rent_compute", "provider": "vast.ai"|"runpod"|"lambdalabs", "instance_type": "...", "estimated_cost_usd_hr": 0.15, "reason": "..." }`. Present this via the HITL gate (user approves before spending).

3. **Actually use rented compute** — once approved, the system calls the remote GPU API (Vast.ai/RunPod), provisions the instance, runs the Ollama server on it, and routes inference calls there transparently. When done, terminates the instance. **All data stays encrypted in transit — no plaintext model inputs to third parties unless the user explicitly approves.**

4. **Cost-first routing logic** — priority order:
   - Free local (llama3.2, gemma3) — always try first
   - Local with offload (qwen2.5:7b, qwen2.5-coder:14b with CPU offload)
   - OpenRouter free tier (meta-llama/llama-3.1-8b-instruct:free etc.)
   - Rented GPU (user-approved, cost-capped, data-safe)
   - Anthropic/OpenAI API (last resort, highest cost)

**Implementation files:**
- `runtime/engine/compute/compute_planner.py` — assess_compute_needs(goal, context_len) → ComputePlan
- `runtime/engine/compute/remote_provisioner.py` — provision/terminate Vast.ai or RunPod instances
- `runtime/core/hitl_gate.py` — extend to handle "rent_compute" approval requests
- `backend/routes/forge.js` — surface compute suggestions in the UI

---

## Why this matters

Right now every agent calls one model (`OLLAMA_MODEL`, defaults to `llama3.2`). The system has no awareness of:
- Which model is currently in VRAM
- Which task type needs which model
- How to offload layers to CPU/RAM when a model is too big for 8 GB
- How to hand context from one model to the next during a multi-step task
- OpenRouter free models as overflow capacity

The infrastructure to compute all of this **already exists** (`turbo_quant.py`, `lifecycle_manager.py`) but is **not wired into actual inference**. This plan closes that gap.

---

## What already exists (do not rebuild)

| Capability | Location | Status |
|---|---|---|
| Quant selection ladder Q8→Q2 | `lifecycle_manager.select_quant()` | Works, not wired |
| VRAM detection (nvidia-smi) | `lifecycle_manager._free_vram_mb()` | Works |
| Model eviction (keep_alive=0) | `llm._ollama_unloader()` | Works |
| Disk/CPU offload calc | `turbo_quant.disk_offload_config()`, `should_offload_to_cpu()` | Computes but never applied |
| Model selection by category | `turbo_quant.select_model(category=)` | Works, not wired to agents |
| OpenRouter backend | `orchestrator.LLMClient` (`openrouter` backend) | Works, no free models in catalogue |
| ReAct agent loop | `engine/agent/agent_loop.py` | Built this session |
| Swarm controller | `core/swarm/swarm_controller.py` | Built this session |

---

## Phase 1 — Fix model catalogue + per-task model selection (2-3 hrs)

**File:** `runtime/agents/turbo-quant/turbo_quant.py`

Replace `_MODEL_CATALOGUE` model names with what's actually installed:

```
tiny_money  → llama3.2:latest        (2.0 GB)  tool selection, fast classify
small_money → gemma3:latest          (3.3 GB)  general tasks
mid_power   → qwen2.5:7b-instruct     (4.7 GB)  reasoning, synthesis
coder       → qwen2.5-coder:14b       (9.0 GB)  code (CPU-offloads ~2 layers)
vision      → llava:latest            (4.7 GB)  multimodal
```

**File:** `runtime/engine/agent/agent_loop.py`

In `_reason()`, detect the pending action and pick the model per step:
- Tool-call reasoning → `llama3.2` (tiny, always hot)
- Code actions → `qwen2.5-coder:14b`
- Research/synthesis → `qwen2.5:7b-instruct`

---

## Phase 2 — CPU/RAM offload applied to inference (2-3 hrs)  ★ KEY GAP

**File:** `runtime/engine/inference/llm.py`

The Ollama `/api/generate` call currently sends NO `options`. Add VRAM-aware offload options computed from the existing `disk_offload_config()`:

```python
def _build_options(model: str, params_b: float, quant: str) -> dict:
    """Compute num_gpu (layers on GPU), num_thread (CPU), num_batch."""
    free_mb = _free_vram_mb()
    cfg = disk_offload_config(params_b, quant)   # existing turbo_quant fn
    opts = {
        "num_thread": min(8, os.cpu_count() or 4),   # CPU threads for offloaded layers
        "num_batch": 256 if (free_mb or 0) < 4000 else 512,
    }
    if free_mb is not None:
        # num_gpu = how many transformer layers to keep on GPU; rest go to CPU/RAM
        opts["num_gpu"] = cfg["gpu_layers_suggested"]
        if free_mb < 2000:
            opts["low_vram"] = True   # Ollama low-VRAM mode
    return opts

# In generate():
payload = {
    "model": chosen_model, "prompt": full_prompt, "system": system,
    "stream": False,
    "options": _build_options(chosen_model, params_b, quant),
}
```

**What this does on your hardware:**
- `qwen2.5-coder:14b` (9 GB) on an 8 GB card → Ollama keeps ~36 of ~40 layers on GPU, offloads the remaining 4 to CPU/RAM automatically. Runs at ~70% speed instead of OOM-crashing.
- When VRAM < 2 GB free → `low_vram: true` shrinks the KV-cache to fit.
- `num_thread` ensures offloaded layers use all CPU cores efficiently.

**File:** `runtime/neural_brain/models/lifecycle_manager.py`

Add a RAM-pressure check alongside VRAM: if system RAM available < 3 GB, prefer the smaller model tier even if VRAM has room (offloaded layers live in RAM, so RAM is the second constraint on a 15 GB box).

---

## Phase 3 — Context handoff between models (1 day)

**File:** `runtime/core/swarm/swarm_controller.py`

When a task switches models (researcher → coder), context must travel. Build a `ContextPacket`:

```python
@dataclass
class ContextPacket:
    goal: str               # original goal — always carried
    findings: str           # summarised output of the previous model
    trajectory_digest: str  # compressed key steps (not full trajectory)
    next_task: str          # specific instruction for the next model
```

`_run_subtask()` passes the upstream subtask's `ContextPacket` as `context` to the next `ReActAgent.run()`. The digest is produced by the cheap `llama3.2` model so summarisation doesn't burn the big model's time. This makes multi-model handoff seamless — each model gets exactly the context it needs, compressed.

---

## Phase 4 — OpenRouter free-tier overflow (1 day)

**File:** `runtime/agents/turbo-quant/turbo_quant.py` — add free models:

```
or_free_general → meta-llama/llama-3.1-8b-instruct:free   (openrouter)
or_free_big     → google/gemma-2-9b-it:free               (openrouter)
or_free_mistral → mistralai/mistral-7b-instruct:free      (openrouter)
```

**Routing rule** in `select_model()`:
- If VRAM full AND RAM under pressure AND task is non-time-critical → route to OpenRouter free
- If local model fails twice → escalate to OpenRouter free
- Respects offline mode (never routes external when `AUTO_RESEARCH_MODE=off` / privacy mode)

This gives the system "overflow capacity" — when the local GPU is saturated, non-urgent work goes to free cloud models instead of queuing.

---

## Phase 5 — On-demand model warming (half day)

**File:** `runtime/engine/inference/llm.py`

Before a task starts, warm the needed model so inference has zero load latency:

```python
def ensure_model_ready(model: str) -> bool:
    free_mb = _free_vram_mb()
    if MODEL_VRAM_MAP.get(model, 5000) > (free_mb or 0) * 0.75:
        _evict_idle_models()              # keep_alive=0 on idle models
    _ollama_post("/api/generate", {"model": model, "prompt": " ", "stream": False}, 30)
    return True
```

Keep `llama3.2` + `nomic-embed-text` permanently resident (`keep_alive: -1`); load/evict the heavy models on demand.

---

## Phase 6 — Model management UI (half day)

**File:** `frontend/src/components/pages/SystemSetupCenter.jsx` (+ ModelsPage already exists)

Show: installed models, VRAM each uses, which is loaded now, RAM/VRAM gauges, one-click pull/evict. Backend route proxies Ollama `/api/tags`, `/api/ps`, `/api/delete`.

---

## Recommended resident stack for 8 GB / 15 GB

| Role | Model | VRAM | Resident? |
|---|---|---|---|
| Fast routing | llama3.2 | 2.0 GB | Always (keep_alive=-1) |
| Embeddings | nomic-embed-text | 0.3 GB | Always |
| Reasoning | qwen2.5:7b-instruct | 4.7 GB | On demand |
| Coder | qwen2.5-coder:14b | 9 GB → CPU offload | On demand only |
| Overflow | OpenRouter free | 0 (cloud) | When local saturated |

---

## Performance fixes already shipped this session

- gzip + brotli pre-compression (React 187→50 KB, Three.js 707→145 KB)
- Express `compression` middleware + pre-compressed `.br`/`.gz` serving
- WS heartbeat 1.8s → 5s; agent poll 5s → 10s
- Merged duplicate clock/uptime intervals in SystemBar, TopBar, TopStrip
- Dashboard payload bounded (last 20 activity / 10 logs / 10 runs)
- Removed broadcaster per-message console.log

---

## Execution order

1. **Phase 2 first** (CPU/RAM offload) — stops OOM crashes, biggest stability win
2. **Phase 1** (catalogue + selection) — foundation for everything
3. **Phase 5** (warming) — removes load latency
4. **Phase 3** (context handoff) — makes multi-model tasks seamless
5. **Phase 4** (OpenRouter overflow) — adds capacity
6. **Phase 6** (UI) — visibility & control

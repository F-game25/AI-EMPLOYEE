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

---

## Phase 7 — Conversation Runtime Layer (real teammate behavior)  ★ added 2026-06-17

This is an **architecture problem, not a prompt bug.** The chat currently behaves like a generic chatbot: it forgets that "optie 2" refers to its own previous answer, it *explains how to check the time manually* instead of fetching it, and it sends a tutorial when one short sentence was asked for. Three failures: **context retention**, **intent detection**, **answer discipline**.

A teammate needs a runtime layer between UI and model:
`user message → intent classifier → context linker → memory/session resolver → tool/action router → response policy → LLM/tool execution → short teammate response`.

### 7.0 Diagnosis of the CURRENT chat pipeline (grounded)

There are **two parallel conversational paths**, and the dumb-chatbot behavior comes from the chat box using the plain one:

| Path | Route | Behaviour |
|---|---|---|
| **Teammate (good)** | `/api/companion/message` → `companion.message` → `runtime/companion/conversation_runtime.py` `ConversationRuntime.handle()` | resolve context → classify intent → select model → broker execute → response (+ critique, clarification) |
| **Legacy (plain)** | `/api/chat` → `backend/services/turn-runner.js` `runTurn()` → `requestPythonChatPayload()` (`backend/server.js:2193`) → Python chat | plain LLM call; **does not** pass through intent/context/policy |

`frontend/src/components/core/ChatPanel.jsx` wires to **both** (`useCompanionStore.sendMessage` *and* `sendChatMessage` over WS). So the UI can silently take the plain path and bypass the teammate runtime entirely.

**What already exists — DO NOT rebuild, integrate:**
- `runtime/companion/conversation_runtime.py` — the turn loop (context → intent → target → act → respond).
- `runtime/companion/intent_classifier.py` — intent classification (returns `mode`, `task_type`, `is_command`, `confidence`).
- `runtime/companion/context_resolver.py` — context resolution.
- `runtime/companion/execution_broker.py` — tool/action routing (`broker.execute(intent, …)`).
- `runtime/companion/safety_gate.py` — the consequential-action gate (ties to the PC-control gate in the quantization plan).

**What is genuinely MISSING (the real fixes):**
1. **Session option-memory + reference resolver** — nothing stores `last_options_given`, so "optie 2 / doe 2 / de tweede / ja die / doe dat" cannot be mapped back. (Verify how far `context_resolver` already resolves references; extend it.)
2. **Response-policy engine** — no rule selecting length/style by intent; the model defaults to long multi-option answers.
3. **System-info tools** — `runtime/tools/` has **no** `local_time` / `hardware` / `cwd` tool, so system questions can only be "explained," never executed. This is the direct cause of the time-question failure.
4. **Single path** — the live chat surface must route through `ConversationRuntime`; the legacy plain path must delegate to it (or be removed), so intent/context/policy always apply.

### 7.1 Components to add / wire

1. **Session Context Manager** — per-chat rolling state available before *every* model call: `current_topic`, `last_user_message`, `last_assistant_message`, `last_options_given:[{id,summary}]`, `pending_decision`, `active_task_state`, `recent_tool_results`. Persist per `session_id` (the companion request already carries `session_id`). Home: extend `runtime/companion/context_resolver.py` + a `state/sessions/<id>.json` (tenant-scoped via existing file-lock).
2. **Option / Reference Resolver** — when the user message matches a selection ("option 2", "doe 2", "de tweede", "pak optie twee", "ja die", "doe dat") **and** `last_options_given` is non-empty, resolve to that option and continue — **never** ask "waar heb je het over?".
3. **Intent Classifier (extend existing)** — ensure these intents exist: `system_info.local_time`, `system_info.hardware`, `file.open/read/write`, `browser.open`, `web.research`, `code.inspect/modify`, `task.start/continue`, `question.simple/complex`, `clarification.answer`, `option.selection`, `command.execute`.
4. **Tool/Action Router (extend broker)** — operational requests call a tool, not a tutorial. Add the missing **system-info tools** to `runtime/tools/` + register in `tools/registry.py` and wire into `execution_broker`: `system.local_time` (OS datetime), `system.hardware` (reuse the `hardware_profiler` from the quantization plan), `system.cwd`.
5. **Response Policy Engine** — choose length/style by intent: simple value → max 1–2 sentences; direct action → confirm + execute + summarize; complex planning → structured allowed; error → short + next best action. No tutorials/multi-option unless explicitly requested.
6. **Conversation Compression** — summarize long history into the rolling session state so the model always knows: what the user is doing, current task, what was just offered, what was selected, what tool/action comes next. (Reuse `runtime/memory/context_db/session_compressor.py`.)
7. **Debug Visibility** — in dev/debug mode surface: detected intent, resolved references, selected tool/action, context objects used, response policy chosen, whether session context was injected.

### 7.2 Hard teammate rules (non-negotiable)
- **The assistant must not explain how the user can do something manually when the system can do it itself.** ("Hoe laat is het?" → call the tool → "Het is 14:37." — never "kijk rechtsonder.")
- After options are offered, a selection reference (`optie 2`, `doe dat`) **always** resolves against `last_options_given` — never a context question.
- Simple operational question → execute / one short answer; no tutorial, no unsolicited options.
- Ask **one** short clarifying question only when genuinely unresolved.

### 7.3 Regression tests (prove the fix)
- **A** — Assistant offered "Option 1: explain manually / Option 2: fetch local time"; user says "option 2" → system resolves it and calls the local-time tool.
- **B** — "what time is it on my pc?" → calls local-time tool, answers in one sentence.
- **C** — "open the file we just discussed" → resolves the file from session context (or one short clarification only if none exists).
- **D** — "do that" → resolves "that" from the previous proposed action.
- **E** — a simple operational question → no long explanation, no options, no tutorial.

### 7.4 Integration requirement & quality bar
Integrate into the existing pipeline — **not** an isolated prototype. Touch points: `frontend/src/components/core/ChatPanel.jsx` + `store/companionStore` (single teammate path), `backend/routes/companion.js`, `backend/services/turn-runner.js` (delegate the chat kind to the companion runtime), `runtime/companion/*`, `runtime/memory/memory_router.py` (session/short-term), `runtime/tools/registry.py` (system tools). **Done = ** remembers the immediate conversation, understands short references, performs actions instead of explaining, short answers for simple requests, uses tools when available, asks only necessary clarification, never loses track after an option is selected.

### 7.5 Execution order
1. **7.0 single-path fix** — route the chat box through `ConversationRuntime` (biggest behavior win).
2. **System-info tools** (7.1.4) — unblocks the time/hardware/cwd class immediately.
3. **Session option-memory + resolver** (7.1.1–7.1.2) — fixes "optie 2".
4. **Response policy** (7.1.5) — answer discipline.
5. **Intent coverage + compression + debug** (7.1.3/6/7).
6. **Regression tests A–E**, then ship.

> Sequence per the user's directive: first inspect the codebase → diagnosis (done above) → exact files → detailed plan → tests → **implement only after the plan is approved.**

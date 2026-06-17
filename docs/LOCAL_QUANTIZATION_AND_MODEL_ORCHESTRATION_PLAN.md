# Local Quantization & Model-Role Orchestration — Research + Implementation/Fix Plan

**Status:** plan (not yet implemented) · **Author:** Claude (Opus 4.8) · **Date:** 2026-06-17
**Anchor:** extends [`docs/MODEL_ORCHESTRATION_PLAN.md`](MODEL_ORCHESTRATION_PLAN.md) (Phases 0–6) — does not replace it.
**Scope:** make Gemma-class **execution/PC-control reasoning** and heavier models run reliably on a moderately-specced PC by adding a *quantization-aware, KV-cache-aware, role-separated* model-selection layer — and a hard safety gate so a weak model never silently drives the PC/browser.

---

## 0. Why this exists (the problem, honestly)

The user wants the system to drive real actions (PC-control, browser-use, website audit, Forge code execution). The hard requirement:

- **Execution / PC-control / browser-use reasoning → minimum a Gemma-4-class local reasoner (Q4/QAT or stronger).** If that model is not available, the system must **block execution, fall back to manual, or ask to install it** — it must **never** silently use a weak model to take consequential PC/browser actions.
- **Coding / patch generation → the best installed coder model** (qwen2.5-coder family). Gemma must **not** be forced for coding.
- **Cheap summaries → small fast model; Vision → best multimodal; Review/safety → strongest reviewer.**

The blocker is hardware: a full/8-bit Gemma-4-12B needs ~13 GB and even E4B 8-bit ≈ 8.9 GB, but this GPU has **8 GB total**. So this cannot be "load Gemma and hope." It needs a real quantization + VRAM-budget + routing layer. The compute logic largely **already exists** (`turbo_quant.py`, `model_lanes.py`, `llm._build_ollama_options`) but is **not quant-aware and not role-gated**.

**Anti-fantasy rule (enforced throughout):** every capability flows
`Project → Goal → Action → Evidence → Quality Gate → Report → Memory`.
Claude/Codex must **not** claim Gemma-4, PC-control, browser-use, or website-audit "works" unless it is actually wired and **measured**. No fabricated success (consistent with the system reality audit, commits `4191ed29`→`185fc2f2`).

---

## 1. Measured reality of THIS box (run, not assumed)

Measured 2026-06-17 via `nvidia-smi`, `free`, `lscpu`, `ollama list/ps`:

| Resource | Measured |
|---|---|
| GPU | **NVIDIA RTX 2070 SUPER — 8192 MiB total**, ~1.9 GB already used by desktop, ~5.8 GB free at idle (driver 580.159.03) |
| RAM | 15 GiB total, **~6.9 GiB available** |
| CPU | AMD Ryzen 5 3600 — 6 cores / 12 threads |
| Ollama | v0.21.2 on `/usr/local/bin/ollama` |
| Installed models | `gemma3:latest` 3.3 GB · `qwen2.5-coder:14b` 9.0 GB · `qwen3.5` 6.6 GB · `qwen2.5:7b-instruct` 4.7 GB · `llava` 4.7 GB · `moondream` 1.7 GB · `llama3.2` 2.0 GB · `llama3.1` 4.9 GB · `llama3` 4.7 GB · `llama3.3` 42 GB |
| Loaded now | `llama3.2` at 3.1 GB runtime, **57%/43% CPU/GPU split**, ctx 4096 |

**Two facts that drive the whole design:**

1. **`gemma4` is NOT installed; `gemma3` (3.3 GB) is.** "Gemma 4" must be a *target-if-installable*, never a hard assumption. The recommended local execution model **today** is `gemma3:4b-it-qat` (int4 QAT, see §2) — which is **not yet pulled**.
2. **Even a 2 GB model already spills 43% to CPU** at ctx 4096. So the *usable* VRAM budget for model weights after desktop + KV-cache is realistically **~4–5 GB, not 8 GB**. Any selection logic that treats "8 GB" as the budget is wrong. Budget must be **live free VRAM minus the planned KV-cache**, measured per request.

---

## 2. Research summary — quantization for moderate hardware (grounded, with sources)

### 2.1 GGUF quantization decision tree
GGUF compresses FP16 weights to 8/6/5/4/3/2-bit. Practical mapping (per HardwareHQ / promptquorum / willitrunai):

| VRAM | Recommended quant | Notes |
|---|---|---|
| < 8 GB | Q3_K_M (cautious), **Q4_K_M if it fits** | this box sits here for ≥7B models |
| 8–12 GB | **Q4_K_M** (sweet spot) | ~70% smaller than FP16, **1–3% quality loss** |
| 12–16 GB | Q5_K_M / Q6_K | Q5_K_M ≈ +1.5% quality vs Q4_K_M |
| 16–24 GB | Q8_0 | near-lossless |

- **Q4_K_M**: 7B FP16 13.5 GB → **4.1 GB**, retains ~92–95% quality. Quality loss is **more noticeable for coding/reasoning** → the **coder** should prefer Q5+ when it fits; **execution reasoning** can run Q4 QAT.
- **Rule:** never auto-pick a quant below the role's `min_quant` floor (§3).

### 2.2 QAT is the key lever (★ most important finding)
**Quantization-Aware Training** bakes int4 robustness into the weights → int4 size with **near-BF16 quality** (~3× less memory than half precision). And it's **already in Ollama**:
- Gemma 3 QAT: `gemma3:1b-it-qat`, `gemma3:4b-it-qat`, `gemma3:12b-it-qat`, `gemma3:27b-it-qat` (Google released Q4_0 QAT for Ollama/llama.cpp/MLX).
- Gemma 4 QAT (E4B/12B) exists too ("~72% VRAM cut, near-original quality").

➡ **On 8 GB VRAM, the execution-reasoning model should be a QAT int4 model**, not a generic Q4 of a full model. `gemma3:4b-it-qat` (~3–4 GB) is the realistic high-quality target **today**; `gemma4:e4b-*-qat` when pulled; `*:12b-it-qat` only with offload + low context.

### 2.3 KV-cache quantization (free VRAM, ~zero quality cost)
- `OLLAMA_KV_CACHE_TYPE=q8_0` → **~½ KV-cache memory**, "very small" precision loss (perplexity +0.002–0.05, undetectable). `q4_0` → ~¼ memory but more loss at long context.
- **Requires `OLLAMA_FLASH_ATTENTION=1`** to take effect.
- ➡ Set **`OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` globally** — near-free headroom on an 8 GB card. (Google **TurboQuant** pushes this much further — ~3-bit KV; see §2.7.)

### 2.4 KV-cache VRAM formula (for the budgeter)
`KV_bytes ≈ 2 × n_layers × n_kv_heads × head_dim × bytes_per_elem × context_len × num_parallel`
(factor 2 = K and V; `bytes_per_elem` = 2 for f16, 1 for q8_0, 0.5 for q4_0). Grows **linearly with context** → context is a first-class VRAM cost, not free.

### 2.5 Ollama runtime knobs for a single 8 GB GPU
- **`num_gpu`** (layers on GPU): partial offload works but is **~5× slower** (measured elsewhere: num_gpu 25 on an 8 GB card → 4.8 GB & 8.6 tok/s vs full 7.2 GB & 40.6 tok/s). ➡ Prefer a quant that **mostly fits**; offload only the last few layers; treat heavy offload as a fallback, not the default.
- **`OLLAMA_NUM_PARALLEL=1`** for heavy models — RAM/VRAM scales by `NUM_PARALLEL × context`.
- **`OLLAMA_MAX_LOADED_MODELS=1`** — one heavy model resident at a time on this box.
- **`keep_alive`**: `-1` for the always-hot tiny router (`llama3.2`); short (e.g. `30s`) for heavy models so they evict fast.

### 2.6 Gemma 4 footprints (secondary sources — verify by measuring, do not hardcode)
E4B ≈ 4.5 GB (Q4_0) / 8.9 GB (8-bit); 12B ≈ 6.7 GB (Q4_0) / 13.4 GB (8-bit) — **base weights only; KV-cache/context add on top.** ➡ On 8 GB: **E4B Q4/QAT is realistic; 12B Q4 only with offload + low ctx; any 8-bit is not realistic.** The profiler/benchmark harness (§5 Phase A0) must replace these estimates with **measured** numbers.

### 2.7 Google TurboQuant — next-gen KV-cache compression ★ the lever for heavier models

> **Naming:** Google **TurboQuant** is NOT the repo's existing `runtime/agents/turbo-quant/turbo_quant.py` (that's our own quant *selector*). TurboQuant is a Google DeepMind algorithm (ICLR 2026, paper Mar 25 2026) for compressing the **KV cache**.

- **What:** a training-free, data-oblivious KV-cache quantizer (Walsh-Hadamard transform → polar/Lloyd-Max quantization → QJL correction) that takes the KV cache down to **~3 bits/value** (2-bit demonstrated) with **no measurable accuracy loss**, ~**5–6× KV-cache memory reduction** and faster attention.
- **Why it matters here:** after model weights, the **KV cache is the #2 VRAM cost** on 8 GB (it grows linearly with context — §2.4). Ollama's built-in `q8_0` KV is only ½; TurboQuant is ~⅙. **Stacking matters:** QAT int4 **weights** (~4× smaller) **+ TurboQuant 3-bit KV** (~5–6× smaller) is what lets a **12B-class model with real context fit in 8 GB**, instead of OOM or tiny-context.
- **Availability (measured June 2026 — verify before relying):**
  - **vLLM:** upstream — `--kv-cache-dtype turboquant_3bit_nc` on stock vLLM for GQA/MHA models (no plugin). Heaviest runtime; best for serving, not ideal as the only local engine on 8 GB.
  - **llama.cpp:** community implementations (e.g. AmesianX/TurboQuant "~5.2× KV reduction", and the **QuantumLeap** fork which exposes an **Ollama-compatible API** and *coexists* with Ollama). Mainline llama.cpp discussion open → likely to land as a standard `--cache-type` and reach Ollama users automatically.
  - **Ollama (stable):** not native yet. Today's native lever stays §2.3 (`q8_0` KV + flash-attn).
- **Recommendation for THIS box (cost/risk ordered):**
  1. **Now:** Ollama `OLLAMA_KV_CACHE_TYPE=q8_0` + `OLLAMA_FLASH_ATTENTION=1` (§2.3) — zero new infra.
  2. **Pilot (heavy models):** install the **QuantumLeap llama.cpp+TurboQuant** fork as a *second, opt-in backend* (Ollama-compatible API, runs alongside Ollama). Route only `execution_reasoning`/heavy tiers to it when present; everything else stays on Ollama. Benchmark real tok/s + VRAM before trusting it.
  3. **Watch:** when mainline llama.cpp/Ollama merge TurboQuant, drop the fork and use the native `--cache-type`.
- **Wire-in (no hardcoding, backend-detected):**
  - `model_quant_profiles.json` / `vram_budget.plan`: add a `turboquant_3bit` KV option (`bytes_per_elem ≈ 0.375` in the §2.4 formula) so the budgeter can show how much more context/model fits with it on.
  - `hardware_profiler`: detect the active inference backend + whether TurboQuant KV is available (vLLM flag present, or QuantumLeap endpoint reachable). Selection uses TurboQuant KV **only when detected**, else falls back to `q8_0` — never assume it's there.
  - `model_roles` gains an optional `kv_cache` preference per role (heavy/long-context roles prefer `turboquant_3bit` when available).
- **Honest status:** this is a real capability with real implementations, but it requires a **backend change** (a llama.cpp fork or vLLM) — not a flag flip on stock Ollama. Treat it as an opt-in pilot with measured benchmarks and graceful fallback, consistent with the anti-fantasy rule (§0): don't claim TurboQuant is active unless the backend actually reports it.

---

## 3. Target architecture — config-driven, no hardcoding

Two new config files (single source of truth, no model names hardcoded in logic):

### 3.1 `runtime/config/model_roles.json`
```jsonc
{
  "execution_reasoning": {                 // PC-control / browser / Forge action decisions
    "tier": "HEAVY", "min_quant": "Q4_K_M",
    "preferred_models": ["gemma4:e4b-it-qat", "gemma3:4b-it-qat", "gemma3:12b-it-qat", "qwen3.5"],
    "required_for": ["pc_control", "browser_action", "forge_action"],
    "on_unavailable": "block_or_manual_or_remote"   // NEVER silently downgrade
  },
  "coding":        { "tier": "CODE", "min_quant": "Q4_K_M",
                     "preferred_models": ["qwen2.5-coder:14b", "qwen2.5-coder:7b"],
                     "never_degrade_to_general": true },
  "cheap_summary": { "tier": "FAST", "preferred_models": ["llama3.2"] },
  "vision":        { "tier": "NORMAL", "preferred_models": ["llava", "moondream"], "text_only_fallback": true },
  "review_safety": { "tier": "HEAVY", "min_quant": "Q5_K_M",
                     "preferred_models": ["qwen3.5", "qwen2.5:14b-instruct", "gemma3:12b-it-qat"] }
}
```

### 3.2 `runtime/config/model_quant_profiles.json`
Per model: a quant ladder `{quant: vram_mb}` — **seeded from research, then overwritten by measured numbers** from the benchmark harness.
```jsonc
{
  "gemma3:4b-it-qat":   { "q4_0": 3600 },            // QAT — int4 only
  "gemma3:12b-it-qat":  { "q4_0": 8200 },            // offload + low ctx on 8 GB
  "qwen2.5-coder:14b":  { "q4_K_M": 7500, "q5_K_M": 10600 },
  "qwen2.5-coder:7b":   { "q4_K_M": 3800, "q5_K_M": 5300 },
  "qwen3.5":            { "q4_K_M": 4600, "q5_K_M": 6600 },
  "llama3.2":           { "q4_K_M": 1300, "q8_0": 2500 }
}
```

**Recommended role map for THIS box (grounded in §1–§2):**

| Role | Model (today) | Quant | ~VRAM | Resident |
|---|---|---|---|---|
| Fast routing / summary | `llama3.2` | Q4_K_M | ~1.3 GB | always (`keep_alive=-1`) |
| Embeddings | `nomic-embed-text` | — | ~0.3 GB | always |
| **Execution reasoning / PC-control** | **`gemma3:4b-it-qat`** *(pull)* → `gemma4:e4b-it-qat` later | int4 QAT | ~3–4 GB | on demand |
| Coding | `qwen2.5-coder:14b` (offload ~4 layers) or pull `:7b` Q5 | Q4_K_M/Q5 | 7.5–9 GB | on demand only |
| Vision | `llava` / `moondream` | Q4 | 1.7–4.7 GB | on demand |
| Review / safety | `qwen3.5` or `qwen2.5:14b` | Q5_K_M | 6.6–10 GB | on demand |
| Overflow | OpenRouter free / rented GPU | — | 0 (cloud) | HITL-gated |

Global Ollama env: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`.

---

## 4. Gap analysis — current code vs target

| Area | Current | Gap |
|---|---|---|
| `runtime/core/model_lanes.py` | tier ladders are fixed `(model, vram_mb)` tuples; `resolve_tier()` picks largest that fits w/ crude **`need ≤ vram*2`** offload heuristic | **not quant-aware**, no QAT entries, no roles; the 2× heuristic is what lets a 2 GB model over-commit and spill to CPU |
| Quant profiles | none | no `model_quant_profiles.json` |
| Roles | none | no `model_roles.json`, no role resolver |
| VRAM budget | `_usable_vram_mb()` reads `ResourceManager.budget.max_vram_mb` | must verify it's **live free VRAM**, and subtract **planned KV-cache** (formula §2.4) — currently context cost is ignored |
| `turbo_quant.py` (1959 ln) | computes `select_quant`, `disk_offload_config`, `select_model`, `log_inference` | computed but **not wired** to role/quant selection or the hard gate |
| `llm._build_ollama_options` | computes `num_gpu` | not quant-aware, doesn't set KV-cache/flash-attn env, doesn't pull `model:quant`, no honest "unavailable" |
| Safety gate | `companion/safety_gate.py`, `hitl_gate.py` exist | **no rule** blocking PC-control when execution model < min — the core requirement is unmet |
| Benchmarks | none | no measured tok/s + real VRAM per `model@quant` |

---

## 5. Implementation plan (phased — files · functions · acceptance)

> Build order favors **truth first** (measure), then selection, then the safety gate. Each phase has an acceptance test; nothing is "done" without measured evidence.

### Phase A0 — Profiler & benchmark harness (measure first) ★ do this first
- **New** `runtime/engine/compute/hardware_profiler.py`: `live_vram_mb()` (parse `nvidia-smi --query-gpu=memory.free`), `ram_available_mb()`, `cpu_threads()`, `ollama_inventory()` (`/api/tags`), `ollama_loaded()` (`/api/ps`, incl. CPU/GPU split). Centralizes/replaces ad-hoc `_free_vram_mb()`.
- **New** `scripts/benchmark_models.py`: for each `(model, quant)` in profiles → warm, run a fixed prompt, record **tok/s, measured VRAM, CPU/GPU split, load ms** → `state/model_benchmarks.json`. Re-runnable.
- **Accept:** `state/model_benchmarks.json` has real numbers for ≥ the recommended stack; `live_vram_mb()` matches `nvidia-smi` ±100 MB.

### Phase A1 — Config-driven profiles + roles
- Add `runtime/config/model_quant_profiles.json` (seed from §2.6/§3.2, then overwrite from A0 measurements) and `runtime/config/model_roles.json` (§3.1).
- **Accept:** both load + JSON-validate in a unit test; profiles cover every model referenced by roles.

### Phase A2 — Quant-aware resolution in `model_lanes.py`
- Add `resolve_tier_with_quant(tier) -> {model, quant, vram_needed, fits, offload_layers}`: walk the model's quant ladder **largest→smallest within the turbo_quant mode floor/ceiling**, pick the highest quant whose `vram_needed + kv_budget ≤ live_free_vram`; else mark `fits=false` + compute `offload_layers`.
- Add `model_and_quant_for_role(role)` using `model_roles.json`. Keep `resolve_tier()` (return `.model`) for backward-compat.
- **Accept:** `resolve_tier_with_quant("HEAVY")` returns a concrete `model@quant` that fits **measured** VRAM; `gemma3:4b-it-qat` is selectable for `execution_reasoning`.

### Phase A3 — KV-cache-aware VRAM budgeter
- **New** `runtime/engine/compute/vram_budget.py`: `plan(model, quant, ctx, parallel=1)` → `{num_gpu, num_ctx, low_vram, kv_cache_type, fits, est_vram_mb}` using the §2.4 formula + live free VRAM. Replaces the `*2` heuristic.
- **Accept:** for `gemma3:4b-it-qat` at ctx 4096 it returns `fits=true, num_gpu=all`; for `qwen2.5-coder:14b` it returns a partial `num_gpu` (a few layers offloaded) instead of OOM.

### Phase A4 — Wire into inference (`runtime/engine/inference/llm.py`)
- `_resolve_quant_model(base_model) -> (model, quant)` (via A2). `ensure_model_available(model, quant)`: check `/api/tags`; `ollama pull model:quant` or return **honest `unavailable`** (never silent OOM). Extend `_build_ollama_options()` to take `(model, quant)` and call `vram_budget.plan(...)`. Log `model, quant, vram, latency` to `state/turbo_quant.log.jsonl`.
- Set global env on startup: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`.
- **Accept:** a generate() call logs the chosen `model@quant` + measured VRAM; KV-cache type is active (verify via `ollama ps` memory drop).

### Phase A5 — Model-role enforcement + hard PC-control gate ★ the safety requirement
- **New** `runtime/core/model_role_resolver.py`: `resolve_role(role) -> {model, quant, available, reason}`, validating `quant ≥ min_quant`.
- **Hard rule:** PC-control / browser / Forge action decisions call `resolve_role("execution_reasoning")`. If `available=false` → **block** the action via `hitl_gate` / degrade to manual / emit `{action:"install_model", model:"gemma3:4b-it-qat", reason:...}`. Wire into `runtime/companion/execution_broker.py` + `safety_gate.py` and the Computer-Use toggle (`/api/computer-use/mode`).
- Coding routes to `CODE` tier only (never Gemma). Cheap/vision/review per roles.
- **Accept (negative test):** with no execution-grade model present, toggling Computer-Use / requesting a PC action **blocks with an install suggestion** — it does **not** run a weak model. Coding requests never resolve to a Gemma model.

### Phase A6 — Lifecycle: one heavy at a time
- Keep `llama3.2` + `nomic-embed-text` resident; before loading a heavy model, evict idle heavies (`keep_alive=0`) if `live_vram` insufficient. Extends existing eviction.
- **Accept:** loading the coder evicts the previous heavy; `llama3.2` stays hot.

### Phase A7 — UI / observability
- Models page: installed models, **loaded-now with CPU/GPU split** (`ollama ps`), VRAM/RAM gauges, benchmark tok/s, current **role→model@quant** resolution, one-click pull (esp. QAT models). New `GET /api/models/roles` + `GET /api/models/benchmarks`.
- **Accept:** page shows live resolution and lets the user pull `gemma3:4b-it-qat`.

### Phase A8 — Overflow (ties to MODEL_ORCHESTRATION_PLAN Phase 0/4)
- When even the smallest quant of the execution model can't fit AND the task needs it → HITL "rent compute" (Vast.ai/RunPod) or OpenRouter free (privacy-gated, never silent). Honest failure otherwise.
- **Accept:** the unavailable path produces a structured, user-approved escalation — not a fabricated result.

---

## 6. First concrete steps (when implementation is approved)

1. `ollama pull gemma3:4b-it-qat` (execution reasoning) — and optionally `gemma3:12b-it-qat`, `qwen2.5-coder:7b`.
2. Land Phase A0 (profiler + benchmark) and record real numbers → `state/model_benchmarks.json`.
3. Land A1–A3 (configs + quant-aware resolution + budgeter), unit-tested against measured data.
4. Land A4 (inference wiring + global Ollama env).
5. Land A5 (role resolver + **hard PC-control gate**) with the negative test.
6. A6/A7/A8 as follow-ups.

**Definition of done:** a measured benchmark report exists; `execution_reasoning` resolves to a QAT/Q4 Gemma-class model that fits **measured** VRAM; PC-control is hard-gated when that model is absent; coding stays on the coder; every inference logs `model@quant` + VRAM + latency; **no model name is hardcoded in selection logic** (all from config + live measurement).

---

## 7. Sources (online research, 2026-06)

- Gemma 4 family & sizes: analyticsvidhya.com/blog/2026/06/google-gemma-4-12b, developers.googleblog.com/gemma-4-12b-the-developer-guide, aitooldiscovery.com/how-to/gemma-4-ollama
- Gemma QAT: developers.googleblog.com/en/gemma-3-quantized-aware-trained-state-of-the-art-ai-to-consumer-gpus, blog.google/innovation-and-ai/technology/developers-tools/quantization-aware-training-gemma-4, x.com/ollama/status/1913220728154935683
- GGUF quant tradeoffs: hardwarehq.io/quantization-guide, promptquorum.com/local-llms/llm-quantization-explained, willitrunai.com/blog/quantization-guide-gguf-explained
- Ollama KV-cache quant + flash attention: docs.ollama.com/faq, modelpiper.com/blog/ollama-kv-cache-quantization, smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama
- Ollama offload / num_gpu / num_parallel: ollama.readthedocs.io/en/faq, localllm.in/blog/ollama-vram-requirements-for-local-llms, eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling
- KV-cache VRAM formula: spheron.network/blog/kv-cache-optimization-guide, pcpartguide.com/blog/kv-cache-explained
- Google TurboQuant (KV-cache 3-bit, ICLR 2026): research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression, en.wikipedia.org/wiki/TurboQuant
- TurboQuant implementations: github.com/ggml-org/llama.cpp/discussions/20969, github.com/AmesianX/TurboQuant, github.com/MartinCrespoC/QuantumLeap---Llama.cpp-TurboQuant (Ollama-compatible), github.com/varjoranta/turboquant-vllm (vLLM `--kv-cache-dtype turboquant_3bit_nc`)

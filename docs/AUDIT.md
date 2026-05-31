# AI-EMPLOYEE System Audit
**Date**: 2026-05-26
**Branch**: wavefield-routing
**Reviewer**: Architecture Reviewer Agent

---

## A. Desktop Shell (Electron)

### Security Configuration

| Setting | Value | Assessment |
|---------|-------|------------|
| `contextIsolation` | `true` (both windows) | Correct |
| `nodeIntegration` | `false` (both windows) | Correct |
| `webSecurity` | `true` (both windows) | Correct |
| `backgroundThrottling` | `false` (appWindow only) | Intentional — prevents WebGL context loss |
| Preload scope | `contextBridge` only, no `require` exposure | Correct |

The Electron main process (`launcher/main.js`) is well-structured. Context isolation is enabled and nodeIntegration is disabled on both the launcher and dashboard windows. The preload script (`launcher/preload.js`) exposes only named IPC wrappers via `contextBridge.exposeInMainWorld('ai', {...})` — no raw `ipcRenderer` or `require` leaks into renderer land.

### Identified Issues

**RAM baseline**: Electron carries a Chromium process tree. With one dashboard window loading Three.js scenes (716KB `vendor-three-core` chunk alone), idle RAM will be 300-500MB minimum on Linux. No measurement exists in the codebase; this is an estimate.

**WebGL workarounds**: The code applies `--ignore-gpu-blocklist`, `--enable-unsafe-swiftshader`, and `--disable-gpu-process-crash-limit` unconditionally. These are defensive for stability but they widen the GPU attack surface. The SwiftShader software fallback is always loaded even on hardware rendering paths.

**Boot metrics feedback loop**: `persistBootMetrics()` writes to `state/boot_metrics.json` on every boot. This is in-repo state, not canonical state (`~/.ai-employee/state/`). The path mismatch is minor but creates a discrepancy.

**F11 fullscreen blocked**: The dashboard window intercepts F11 at `before-input-event` to prevent WebGL context loss on Linux — a pragmatic Linux-specific workaround, but not documented for Windows/macOS users.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `launcher/main.js` | Electron main process, IPC, window lifecycle | 🟢 Real+Connected | Node backend via health checks, preload via IPC | RAM profiling, no memory cap | Medium | P2 |
| `launcher/preload.js` | contextBridge IPC surface (v4) | 🟢 Real+Connected | Renderer, main process | None | Low | P3 |
| `launcher/src/backend.js` | Spawns start.sh, tail logs, phase tracking | 🟢 Real+Connected | start.sh, health checks | | Low | P3 |
| `launcher/src/health.js` | HTTP probes /api/health, port checks | 🟢 Real+Connected | Node :8787, Python :18790 | | Low | P3 |
| WebGL stability flags | SwiftShader fallback, GPU flags | 🟡 Stub/Demo | Renderer | Hardware perf benchmarking | Low | P3 |

---

## B. Frontend (React)

### Structure

- **58 pages** in `frontend/src/components/pages/`
- **10 Zustand stores** in `frontend/src/store/`
- **React 19**, Vite 8, react-router-dom v7
- **Heavy dependencies**: three.js, @react-three/fiber, @react-three/drei, framer-motion, react-force-graph-3d

### Bundle Size Analysis

| Bundle | Size | Notes |
|--------|------|-------|
| `vendor-three-core-*.js` | 716KB | Three.js core — loaded eagerly |
| `KnowledgePage-*.js` | 384KB | Abnormally large page chunk |
| `NeuralNetworkPage-*.js` | 340KB | Expected (3D scene) |
| `vendor-three-extras-*.js` | 196KB | Three.js extras |
| `vendor-react-*.js` | 196KB | React runtime |
| `framer-motion-*.js` | 140KB | Animation library |
| `Dashboard-*.js` | 56KB | Core layout |
| Total assets | ~4.2MB | Compressed; uncompressed significantly higher |

**Total JS parse cost on first load**: approximately 2MB+ of JavaScript that must be parsed before any interactivity. On a mid-range device this will produce a >3s Time to Interactive.

### Performance Issues

**`KnowledgePage` at 384KB is the largest page chunk** — larger than the entire Dashboard shell. This suggests either unguarded imports of the Three.js vendor bundle from within the page, or a missing dynamic import boundary.

**No Suspense boundary around Three.js pages**: `NeuralNetworkPage` (340KB) and related 3D pages are lazily imported, which is correct. However `KnowledgePage` at 384KB deserves investigation — if it includes 3D dependencies, it should be split further.

**`App.jsx` architecture**: The Dashboard itself is lazy-loaded (`lazy(() => import('./components/Dashboard'))`), which is correct. `ContextCheckModal` is imported synchronously and always mounted — minimal cost but mounts globally regardless of route.

**Readiness polling**: `App.jsx` polls `/api/readiness` every 1500ms until system is ready, then stops. An 8-second hard timeout forces `degraded` mode if the backend is slow. This is pragmatic but means every boot with a slow Python backend produces a degraded-mode dashboard.

**`bootstrapWsStore`**: The WebSocket store is initialized inside a `useEffect` that fires after the JWT token fetch. If the token fetch fails (network error), `bootstrapWsStore()` still runs — queued WS events may replay against an unauthenticated context.

### State Management

10 Zustand stores cover: agents, app state, learning, security, economy, cognition, system, brain, event feed, tasks. No Redux or Recoil. Zustand is appropriate for this scope.

**Risk**: No persistence layer for Zustand stores. On browser refresh or page navigation, all in-memory state (agent grades, cognition state, task progress visible in UI) is lost and must re-fetch from API. For a 58-page application with heavy real-time data this produces visible loading flicker on every navigation.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `App.jsx` | Boot sequence, readiness polling, auth token | 🟢 Real+Connected | /api/readiness, /api/auth/auto-token, WebSocket | No retry on token failure | Medium | P2 |
| Zustand stores (10) | Client state management | 🟢 Real+Connected | API layer | No persistence (all ephemeral) | Low | P3 |
| `Dashboard` (lazy) | Main shell router | 🟢 Real+Connected | All 58 pages | | Low | P3 |
| `KnowledgePage` (384KB) | Knowledge browser | 🟡 Stub/Demo | /api/memory/* | Oversized chunk — audit imports | High | P1 |
| `NeuralNetworkPage` (340KB) | 3D neural graph | 🟢 Real+Connected | /api/neural-brain/* | | Low | P3 |
| Three.js vendor (716KB) | 3D rendering | 🟢 Real+Connected | NeuralNetwork, Graph pages | No WebWorker offload | Medium | P2 |
| `ContextCheckModal` | Research approval gate | 🟢 Real+Connected | WebSocket `task:context_check` | | Low | P3 |

---

## C. Python Engines

### Service Architecture

**Python AI backend**: FastAPI/uvicorn at port 18790, spawned by `start.sh`. The server (`runtime/agents/problem-solver-ui/server.py`) contains approximately **382 route definitions** across 27,000+ lines — this is an extreme monolith.

### Endpoint Coverage

The server registers `/health` and `/health/detail` endpoints. Node backend probes `/api/health` (proxied via Node) and Python's native `/health`.

### Critical Issue: 12GB Log File

`state/python-backend.log.20260515T230320Z.1.log` at **12GB / 716,545 lines** reveals a catastrophic logging loop. The root cause:

- `MetricsCollector` publishes `metrics_tick` events every 1 second via `EventStream.publish()`
- `EventStream.publish()` calls subscribers synchronously — each call invokes SQLite writes to `observability_events.db`
- The Python SSE endpoint at `/api/events` registers a subscriber that calls `loop.call_soon_threadsafe(_enqueue_drop_oldest, evt)`
- When no SSE consumer is connected, the asyncio queue fills (maxsize=512). **Prior to the current fix**, `put_nowait` raised `QueueFull`, which Python's default exception handler serialized the entire 512-item queue to the log as a repr string — each serialization was multi-kilobyte
- This ran **157,296 times** in a single session, generating 12GB

**The fix (`_enqueue_drop_oldest`) is now in place** in the current code. The historical log remains and should be deleted — it consumes 12GB of disk and provides no diagnostic value.

### LLM Routing

`runtime/core/orchestrator.py` implements real LLM routing with:
- Anthropic API (primary)
- Ollama (local fallback, auto-detected via 1s HTTP probe)
- OpenRouter (via `openrouter_client.py`)
- Provider failover via `wavefield_provider.py` (current branch feature)

`runtime/core/llm_router.py` is real — reads from `~/.ai-employee/model-routing.json`, falls back to hardcoded defaults, no stubs.

### Blocking calls

The server uses `run_in_threadpool` from `fastapi.concurrency` for CPU-bound work. However, the MetricsCollector loop runs in a `threading.Thread` with `time.sleep(1.0)` — this is correct for I/O work but every `publish()` call performs a synchronous SQLite `INSERT`. Under load (every second), this creates 1 write/second to `observability_events.db` regardless of whether any consumer is connected.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| FastAPI server (18790) | 382-route Python backend | 🟢 Real+Connected | Anthropic API, Ollama, SQLite | Monolith — no route segmentation | High | P1 |
| `/health` endpoint | Liveness check | 🟢 Real+Connected | Node health probes | | Low | P3 |
| `LLMClient` | Anthropic/Ollama routing | 🟢 Real+Connected | Anthropic API, Ollama :11434 | | Low | P3 |
| `MetricsCollector` | 1Hz metrics tick | 🟢 Real+Connected | EventStream, SQLite | Fix applied; 12GB historical log undeleted | High | P1 |
| `EventStream` | SQLite-backed pub/sub | 🟢 Real+Connected | observability_events.db | Unbounded table growth | Medium | P2 |
| `SandboxManager` | RestrictedPython subprocess execution | 🟢 Real+Connected | Agent code | No cgroup/namespace isolation | High | P1 |
| `unified_pipeline.py` | 10-phase LLM pipeline | 🟢 Real+Connected | LLMClient, tool registry | | Low | P3 |
| `auto_research_agent.py` | Adaptive web research | 🟢 Real+Connected | BRAVE/BING APIs, vector store | No circuit breaker on external APIs | Medium | P2 |

---

## D. AI Model Loading

### Neural Brain Architecture

`runtime/neural_brain/` supports 8 model architectures: LLM, SLM, MoE, VLM, MLM, LAM, LCM, SAM.

### Model Resolver

`runtime/neural_brain/models/model_resolver.py` is real: it queries the local Ollama `/api/tags` endpoint, inspects installed models, classifies hardware tier (via psutil or CPU count), and maps each architecture to the best available installed model. This is hardware-aware, not hardcoded.

### Quantization

Quantization is referenced in:
- `runtime/agents/neural_network/quantize.py`
- `runtime/agents/turbo-quant/turbo_quant.py`
- `runtime/neural_brain/models/model_resolver.py` (reads `quantization_level` from Ollama metadata)
- `runtime/engine/inference/llm.py`

These rely on Ollama's built-in GGUF quantization support. No `bitsandbytes` or `llama.cpp` direct integration — all quantization is delegated to Ollama at the model serving layer.

### Architecture Backends

All 8 backends are implemented with real Ollama calls:
- **LLM**: routes via `core.orchestrator.get_llm_client` + `core.model_routing.select_model_route` — real
- **SLM**: phi3:mini / qwen2.5:1.5b via Ollama — real
- **MoE**: mixtral:8x7b / qwen2.5-moe via Ollama — real (degrades gracefully if not installed)
- **VLM**: moondream / qwen2.5-vl / bakllava via Ollama — real
- **LAM**: qwen2.5-coder:14b / llama3.1 via Ollama — real
- **SAM**: auto-downloads SAM ViT-B checkpoint from Meta CDN — real but requires network on first use
- **LCM**: SimianLuo/LCM_Dreamshaper_v7 via diffusers — real but GPU required; no graceful CPU fallback
- **MLM**: embedding models via Ollama or sentence-transformers — real

**Critical gap**: SAM and LCM auto-download large model checkpoints (375MB for SAM ViT-B; >1GB for LCM) from external CDNs on first use with no explicit user consent gate, no progress feedback, and no offline-mode guard.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `ModelArchitectureRouter` | 8-arch dispatch with retry/backoff | 🟢 Real+Connected | All 8 backends | | Low | P3 |
| `model_resolver.py` | Hardware-aware model selection | 🟢 Real+Connected | Ollama /api/tags | No GPU VRAM check | Medium | P2 |
| LLM backend | Anthropic/Ollama routing | 🟢 Real+Connected | orchestrator.LLMClient | | Low | P3 |
| SLM/MoE/VLM/LAM backends | Local Ollama routing | 🟢 Real+Connected | Ollama | Models must be pre-pulled | Medium | P2 |
| SAM backend | Image segmentation | 🟡 Stub/Demo | Meta CDN (download), PyTorch | Auto-downloads 375MB; no offline guard | High | P1 |
| LCM backend | Image generation | 🟡 Stub/Demo | HuggingFace (download), diffusers | Auto-downloads >1GB; GPU required | High | P1 |
| `middleware.py` SAM inference | Vision pipeline integration | 🔴 Broken/Crash | SAM backend | `raise NotImplementedError("SAM real inference not wired yet")` | High | P1 |

---

## E. RAG + Memory

### Memory Layers

The system implements a 3-layer memory architecture:

1. **Short-term cache** (`runtime/memory/short_term_cache.py`): In-process TTL cache
2. **Vector store** (`state/vector_store.json`): JSON-backed with TF-IDF embeddings (18 entries, real data — marketing tips, etc.)
3. **ChromaDB** (`state/neural_brain/chroma/`): PersistentClient with 5 collections (episodic, semantic, procedural, outcome, interactions) — **directory exists but is empty (4KB)**
4. **Native graph store** (`state/native_memory_graph.db`): SQLite-backed graph — present and non-empty
5. **Neo4j** (`state/neural_brain/neo4j/`): 16KB data directory — present but minimal

### State File Schema

`state/knowledge_store.json`: Schema is `{"topics": {...}}` with topic arrays containing research entries. This is real data — contains Wikipedia research on vector databases, etc.

`state/vector_store.json`: Schema is `{"entries": [...], "count": 18}`. Embeddings are sparse TF-IDF vectors (many zeros, pattern `[0.0, 0.37..., 0.0, ...]`). These are not dense semantic embeddings — the JSON vector store uses a bag-of-words approach, not a real embedding model.

**Finding**: ChromaDB is installed and the adapter is wired, but the ChromaDB collections contain no data (4KB directory). All 18 vector entries live in the JSON fallback store with bag-of-words embeddings. Real semantic search (cosine similarity over dense embeddings) is not operational.

### State Directory Split

Two active state directories exist:
- `~/.ai-employee/state/`: **115 files** — canonical runtime state, used by production agents
- `AI-EMPLOYEE/state/`: **46 files** — repo-local state, used by Electron boot metrics, some legacy modules

`runtime/core/state_paths.py` resolves `STATE_DIR` env var → `AI_EMPLOYEE_STATE_DIR` → `~/.ai-employee/state/` (canonical). The split is intentional but creates confusion: `state/python-backend.log` (repo) vs `~/.ai-employee/state/task_history.jsonl` (canonical).

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `memory_router.py` | Unified memory interface (episodic/semantic/procedural) | 🟢 Real+Connected | vector_store, short_term_cache, strategy_store, ChromaDB | | Low | P3 |
| `vector_store.json` | JSON TF-IDF vector store (18 entries) | 🟡 Stub/Demo | memory_router | Dense embeddings not used; ChromaDB empty | High | P1 |
| ChromaDB adapter | Persistent vector DB | 🔴 Broken/Crash | chroma collections | Collections empty; no data ingestion running | High | P1 |
| `native_memory_graph.db` | SQLite graph store | 🟢 Real+Connected | `NativeGraphStore` | | Low | P3 |
| Neo4j adapter | Graph DB (optional) | 🟡 Stub/Demo | Neo4j (local Docker) | Minimal data; optional per CLAUDE.md | Low | P3 |
| `knowledge_store.json` | Research topic storage | 🟢 Real+Connected | AutoResearchAgent, memory pipeline | | Low | P3 |
| `strategy_store.py` | Learning outcome storage | 🟢 Real+Connected | memory_router | | Low | P3 |

---

## F. Security / OSINT / Blacklight

### Security Headers (Node)

Helmet is configured with:
- CSP: `default-src 'self'`, `script-src 'self' 'unsafe-inline'` — **`unsafe-inline` scripts weakens XSS protection**
- `frameAncestors: 'none'` — correct (clickjacking protection)
- `crossOriginEmbedderPolicy: false` — disabled (required for SharedArrayBuffer/WebAssembly)

### Route Authentication Coverage

| Metric | Value |
|--------|-------|
| Total Node route definitions | ~198 |
| Protected with `requireAuth` | ~97 (~49%) |
| Unprotected | ~101 (~51%) |

**Sensitive unprotected routes identified**:
- `GET /api/audit/events` — audit log readable without auth
- `GET /api/audit/stats` — audit statistics without auth
- `GET /api/blacklight/status` — security status without auth
- `GET /api/blacklight/alerts` — threat alerts without auth
- `DELETE /api/neural-brain/memory/:id` — memory deletion without auth
- `GET /api/workspace/files` — file listing without auth
- `POST /api/workspace/upload` — file upload without auth (critical)
- `GET /api/agents/list` — agent enumeration without auth
- `GET /api/agents/:agent_id/grade` — agent grades without auth
- `GET /api/history` / `GET /api/tasks/:taskId` — task history without auth

### Internal Events Endpoint

`POST /internal/events` is protected by IP allowlist (loopback only). This is the correct pattern for a localhost-only bridge. No auth token is required, which is acceptable given the network restriction.

### Blacklight

`backend/security/blacklight_tools.js` defines 60+ OSINT tool definitions with mode enforcement (`safe`, `passive_network`, `defensive_simulation`, `blocked`). Active scanning tools (port scanner, traceroute, ping sweep, banner grabbing, social media scraper) are marked `blocked`. This is correctly structured as a defensive catalog with execution gating.

### Sandbox

`runtime/core/sandbox_manager.py` uses RestrictedPython + subprocess isolation. However:
- No cgroup memory/CPU limits applied to subprocess
- No network namespace isolation (agent subprocess can make arbitrary network calls)
- No seccomp filter

This means a malicious or buggy agent can consume unlimited resources or exfiltrate data via network calls.

### Self-Evolution

`runtime/core/self_evolution/safe_deployer.py` calls `subprocess.run(apply_cmd, ...)` to apply patches to the live repo. This is only gated by `EVOLUTION_MODE` environment variable. No cryptographic signing of patches. An injection into the patch generation pipeline (`patch_generator.py`) would result in arbitrary code being applied to the running system.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| Helmet CSP | XSS/frame protection | 🟡 Stub/Demo | All HTTP responses | `unsafe-inline` scripts weakens XSS | High | P1 |
| `requireAuth` middleware | JWT token verification | 🟢 Real+Connected | All protected routes | 51% routes unprotected | Critical | P0 |
| `blacklight_tools.js` | OSINT catalog + mode gating | 🟢 Real+Connected | Security panel UI | | Low | P3 |
| `sandbox_manager.py` | RestrictedPython subprocess | 🟡 Stub/Demo | Agent execution | No cgroup/network namespace | High | P1 |
| `safe_deployer.py` | Self-evolution patch application | 🔴 Broken/Crash | Repo filesystem | No patch signing; arbitrary code risk | Critical | P0 |
| `/api/workspace/upload` | File upload (unauthenticated) | 🔴 Broken/Crash | Workspace filesystem | No auth; path traversal risk | Critical | P0 |

---

## G. Remote Compute

`backend/compute_fabric/index.js` implements the compute fabric module. Key findings:

- **All provider adapters have `enabled: false`**: RunPod, Vast.ai, Lambda, NVIDIA DGX Cloud are registered in the provider registry but disabled
- **Daily spend cap defaults to $0**: `COMPUTE_DAILY_CAP_USD=0` by default — no spending possible
- **`COMPUTE_FABRIC_LIVE=1` required**: real purchases are physically blocked without this env var set
- **Dry-run is the default**: all cost-path operations return a PLAN, not a charge
- **Approval token system**: single-use owner approval tokens required for any real spend

This module is correctly structured for safety — it is a **planning stub** that cannot spend money in its current configuration. No credentials are wired.

Local GPU detection via `nvidia-smi` is real. The cost estimates use hardcoded $/hr values (e.g., H100-80G at $3.29/hr) which are indicative only.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `compute_fabric/index.js` | GPU rental planning + cost estimation | 🟡 Stub/Demo | nvidia-smi (local), provider APIs (disabled) | Provider credentials, live mode | Low | P3 |
| Local GPU detection | `nvidia-smi` query | 🟢 Real+Connected | System GPU | | Low | P3 |
| RunPod/Vast.ai/Lambda adapters | Remote GPU provisioning | ⚪ Dead code | Provider APIs | Not implemented; `enabled: false` | Low | P3 |

---

## H. Money Mode

### Pipeline Analysis

`runtime/core/money_mode.py` implements three pipelines:

**`run_content_pipeline`**: Content generation → posting → tracking
- Content generation: calls internal LLM pipeline (real)
- Posting: calls `_step_schedule_post` which enqueues to ActionBus (real infrastructure, but external platform APIs not wired)
- ROI tracking: computed from hardcoded multipliers (`_CONTENT_ROI_MULTIPLIER = 0.03`)
- Status: **partially real** — LLM generation is real, platform posting is not wired to real social APIs

**`run_lead_pipeline`**: Data scraping → filtering → storage
- Scraped record count: computed as `max(len(source) * 4, 10)` — this is **arithmetic on string length, not real scraping**
- Lead filtering: `max(min(scraped_records // 3, ...), 1)` — **entirely computed, no real scraping**
- Storage: writes to `pipeline_store` (real)
- Status: **stub** — no real data scraping occurs

**`run_outreach_pipeline`**: Outreach → response tracking → conversion
- Uses hardcoded rates: `_OUTREACH_RESPONSE_RATE = 0.25`, `_OUTREACH_CONVERSION_RATE = 0.35`
- Response tracking: simulated
- Status: **stub** — no real email sending, response tracking, or conversion measurement

**Stripe integration** (`runtime/core/stripe_integration.py`): Real Stripe SDK calls, but `STRIPE_API_KEY` defaults to empty string. With no key, all methods return `None` and log a warning. No credentials are configured.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| Content pipeline — LLM step | AI content generation | 🟢 Real+Connected | LLMClient | | Low | P3 |
| Content pipeline — posting step | Platform publishing | 🟡 Stub/Demo | ActionBus | Social API credentials (Twitter, LinkedIn) | Medium | P2 |
| Lead pipeline | Data scraping + filtering | 🔴 Broken/Crash | Nothing | Arithmetic stub; no real scraping | High | P1 |
| Outreach pipeline | Email outreach + conversion | 🔴 Broken/Crash | Nothing | Hardcoded rates; no real sends | High | P1 |
| Stripe integration | Payment processing | 🟡 Stub/Demo | Stripe API | STRIPE_API_KEY not configured | Medium | P2 |
| ROI tracking | Revenue record keeping | 🟢 Real+Connected | pipeline_store | Based on simulated data | Medium | P2 |

---

## I. State Files Health

### Directory Authority

| Path | File Count | Authority |
|------|------------|-----------|
| `~/.ai-employee/state/` | 115 | Canonical (runtime agents, Python backend) |
| `AI-EMPLOYEE/state/` | 46 | Repo-local (boot metrics, Electron, legacy modules) |

### Critical State Issues

**12GB orphaned log**: `state/python-backend.log.20260515T230320Z.1.log` (12GB) is from a resolved QueueFull loop. Should be deleted — it provides no diagnostic value and consumes significant disk.

**`observability_events.db`**: 18.7MB SQLite database. The EventStream inserts every published event with no TTL or cleanup. At 1 event/second (metrics_tick) this grows by ~87KB/day indefinitely. No rotation or pruning mechanism exists.

**`learning_engine.json`**: 4.97MB — this is large for a JSON state file. Content not inspected but likely unbounded growth.

**`telemetry.jsonl`**: 17.2MB — append-only telemetry log with no rotation configured (the `_rotate_log_if_large` function in `start.sh` only covers the three main logs, not telemetry.jsonl or observability_events.db).

**`bus.jsonl`**: 3.2MB — message bus event log. Also append-only.

**Vector store quality**: The JSON vector store contains 18 entries with sparse TF-IDF embeddings (many zero values). This is not a real semantic vector store. ChromaDB collections are empty — real RAG requires ChromaDB to be populated.

**`polymarket-trader/trader.py`**: `PolymarketClient.place_order_yes/no` raise `NotImplementedError`. This agent cannot execute any real trades.

| Component | What it does | Real/Stub/Broken | Connects to | Missing | Risk | Priority |
|-----------|-------------|-----------------|-------------|---------|------|---------|
| `~/.ai-employee/state/` | Canonical runtime state | 🟢 Real+Connected | All agents, Python backend | | Low | P3 |
| `state/python-backend.log.*.log` (12GB) | Orphaned crash log | 🔴 Broken/Crash | Nothing | Should be deleted | Medium | P1 |
| `state/observability_events.db` (18.7MB) | Event stream persistence | 🟢 Real+Connected | EventStream | No TTL/pruning | Medium | P2 |
| `state/telemetry.jsonl` (17.2MB) | Telemetry log | 🟢 Real+Connected | Telemetry pipeline | No rotation | Low | P3 |
| `state/vector_store.json` | TF-IDF vector store | 🟡 Stub/Demo | memory_router | Sparse embeddings; ChromaDB empty | High | P1 |
| `state/knowledge_store.json` | Research topic storage | 🟢 Real+Connected | AutoResearchAgent | Schema: `{topics: {...}}` | Low | P3 |
| `state/native_memory_graph.db` | SQLite graph | 🟢 Real+Connected | NativeGraphStore | | Low | P3 |

---

## Summary: Real vs Stub vs Broken

| Category | Real+Connected | Stub/Demo | Broken/Crash | Dead Code |
|----------|---------------|-----------|--------------|-----------|
| Electron shell | 4 | 1 | 0 | 0 |
| Frontend/React | 5 | 1 | 1 | 0 |
| Python backend/routing | 6 | 0 | 2 | 0 |
| AI model loading | 6 | 2 | 1 | 0 |
| RAG + Memory | 4 | 2 | 1 | 0 |
| Security | 2 | 2 | 3 | 0 |
| Remote compute | 1 | 1 | 0 | 3 |
| Money mode | 2 | 2 | 2 | 0 |
| State files | 4 | 1 | 1 | 0 |

---

## Priority Issue List

### P0 — Critical (Immediate Action Required)

1. **`/api/workspace/upload` is unauthenticated**: File upload endpoint accepts files without JWT. Combined with path handling, this is a potential arbitrary file write. Add `requireAuth` immediately.

2. **`safe_deployer.py` has no patch signing**: The self-evolution system applies git patches via `subprocess.run()` with no cryptographic verification of patch provenance. An injected patch at the generation step results in arbitrary code execution on the live system. Gate evolution behind signed patch hashes or disable `AUTO` mode.

3. **~51% of Node routes are unauthenticated**: Sensitive routes including audit log access, memory deletion, agent enumeration, task history, and blacklight alerts are publicly accessible. This assumes local deployment but violates defense-in-depth.

### P1 — High (Fix Within Sprint)

4. **Delete 12GB orphaned log**: `state/python-backend.log.20260515T230320Z.1.log` should be deleted manually — it serves no diagnostic purpose and wastes disk.

5. **ChromaDB empty — RAG is not operational**: All 18 vector entries use sparse TF-IDF. Real semantic retrieval requires ChromaDB to be populated. The auto-research agent is storing research in `knowledge_store.json` but not in ChromaDB collections. Wire the ingestion pipeline.

6. **`middleware.py` SAM inference raises `NotImplementedError`**: The vision pipeline integration point for SAM is explicitly unimplemented. Any code path reaching this will crash. Either remove the dead branch or complete the integration.

7. **Lead and outreach money mode pipelines are arithmetic stubs**: `run_lead_pipeline` computes "scraped records" as `len(source) * 4`. This is meaningless. If these pipelines are presented to users as functional, this is a correctness lie.

8. **SAM/LCM auto-download without user consent**: Both backends silently download 375MB–1GB+ model files from external CDNs on first invocation. This breaks offline-first policy and will surprise users.

9. **`observability_events.db` has no pruning**: Growing at ~87KB/day with no TTL mechanism. Add a cleanup job or implement rolling window deletion.

10. **`KnowledgePage` 384KB chunk**: Investigate imports — likely a missing dynamic import boundary pulling in 3D or vendor dependencies.

### P2 — Medium (Next Sprint)

11. **`unsafe-inline` in CSP script-src**: Weakens XSS protection. Migrate to CSP nonces or hashes for inline scripts.

12. **No cgroup/namespace isolation in SandboxManager**: Agent code running in subprocess can consume unlimited resources and make arbitrary network calls. Add resource limits.

13. **`observability_events.db` write-per-second**: 1 SQLite write/second (metrics_tick) is fine at idle but will contend under load. Consider batching or switching to an in-memory ring buffer with periodic flush.

14. **Stripe not configured**: `STRIPE_API_KEY` is empty — billing is a no-op. This is acceptable if billing is not yet launched, but the UI may present billing features that silently fail.

15. **Zustand stores have no persistence**: 58-page dashboard loses all UI state on navigation. Implement selective persistence for high-value state (agent grades, cognition snapshots).

---

## Electron vs Tauri Decision Matrix

### Context

- Current Electron: `contextIsolation: true`, `nodeIntegration: false` — correctly hardened
- GPU/WebGL instability on Linux requires workaround flags
- RAM baseline: ~300-500MB idle (Chromium process tree + Three.js)
- Python backend communicates via HTTP (not Electron IPC)
- No native module dependencies in Electron that would break on migration

### Decision Matrix

| Criterion | Weight | Electron (current) | Electron+hardened | Tauri v2 | Hybrid (Tauri shell + Electron embedded) |
|-----------|--------|--------------------|------------------|---------|------------------------------------------|
| RAM idle (estimate) | 20% | 2 (~400MB) | 2 (~400MB) | 5 (~50MB) | 3 (~200MB) |
| Security model | 20% | 3 (correct but CSP/route gaps) | 4 (after CSP fixes) | 5 (Rust, minimal attack surface) | 4 |
| Dev speed / migration cost | 15% | 5 (no change) | 5 (incremental fixes) | 1 (full rewrite of launcher) | 2 (high complexity) |
| Breakage risk | 15% | 5 (none) | 4 (minor) | 2 (high — IPC model changes) | 1 (very high) |
| Python integration | 15% | 5 (HTTP, works today) | 5 (HTTP, works today) | 5 (HTTP, works today) | 4 |
| Future scalability | 15% | 3 (Chromium RAM per window) | 3 | 5 (lightweight, updatable) | 3 |
| **Weighted score** | 100% | **3.65** | **3.85** | **3.90** | **2.85** |

### Decision Trigger Rule Evaluation

- **RAM > 800MB idle**: Estimated at 300-500MB. **Trigger NOT met.** (Theoretical; no live measurement exists.)
- **`nodeIntegration=true` with no context isolation**: Both are false/true respectively. **Trigger NOT met.**
- **Python IPC latency > 100ms**: HTTP over loopback typically < 5ms. **Trigger NOT met.**

### Recommendation: Electron + Hardened (Option 2)

**Do not migrate to Tauri at this time.** The migration cost is disproportionate to the gain:

1. The three decision triggers that would mandate migration are not met
2. The Electron launcher is already correctly hardened (context isolation enabled, nodeIntegration disabled)
3. The 58-page React frontend is Vite-based and has no Electron-specific APIs — it communicates with the backend via HTTP, not Electron IPC. A Tauri migration would not require rewriting the frontend but would require rewriting the entire launcher (main.js = 1,100 lines of boot logic, health checking, phase tracking, crash recovery, WebGL mode management)
4. The Python backend communicates via HTTP regardless of shell technology — no IPC advantage from Tauri

**Instead, apply these hardening measures to the current Electron shell:**

1. Replace `'unsafe-inline'` in `script-src` CSP with nonces (Vite supports CSP nonces in build output)
2. Add `COMPUTE_FABRIC_LIVE` and `EVOLUTION_MODE` validation at launch time with explicit user confirmation
3. Implement RAM telemetry in the launcher (use Electron's `process.getProcessMemoryInfo()`) and surface it in the boot metrics dashboard
4. Remove the 12GB orphaned log

**Migration risk assessment for Tauri**: High. The boot phase tracking system (7 phases, exponential backoff health probes, crash recovery, auto-restart logic, Python subsystem timing ingestion) would all need to be re-implemented in Rust/Tauri IPC. The current launcher has significant operational history embedded in it (WebGL mode persistence, render preference file, first-boot detection, native module ABI checking). Estimated migration: 3-4 weeks engineering time with high regression risk during the transition period.

**Revisit Tauri migration** if: (a) measured idle RAM exceeds 800MB, (b) the system moves to packaged distribution where Electron binary size (~100MB) is a distribution concern, or (c) a second concurrent Electron window is added (doubles RAM).

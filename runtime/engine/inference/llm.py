"""Engine — Inference: LLM generation and embedding via Ollama or ai_router."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.model_routing import select_model_route

# ── Model size map (params_b) for installed Ollama models ─────────────────────
# Used by _build_ollama_options to compute num_gpu layers.
_MODEL_PARAMS_B: dict[str, float] = {
    "llama3.2":              3.2,
    "llama3.2:latest":       3.2,
    "gemma3":                4.0,
    "gemma3:latest":         4.0,
    "qwen2.5:7b-instruct":   7.0,
    "qwen2.5-coder:14b":    14.0,
    "llava":                 7.0,
    "llava:latest":          7.0,
    "qwen3.5":               7.0,
    "nomic-embed-text":      0.1,
}

logger = logging.getLogger("engine.inference")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
DEFAULT_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_TIMEOUT = int(os.environ.get("ENGINE_INFERENCE_TIMEOUT", "120"))


@dataclass(frozen=True)
class RouteDecision:
    tier: str
    estimated_tokens: int
    chosen_model: str


def _route_model(prompt: str, context: str | None, requested_model: str | None) -> RouteDecision:
    default_model = requested_model or DEFAULT_MODEL
    route = select_model_route(prompt=prompt, context=context, requested_route=None, default_route="auto")
    is_long = route.tier == "long" and route.model_route == "wavefield"
    return RouteDecision(
        tier="long" if is_long else "short",
        estimated_tokens=route.estimated_tokens,
        chosen_model=(route.force_model or default_model) if is_long else default_model,
    )

# Optional ai_router integration — resolved lazily on first call to avoid
# import-time path-manipulation side effects and allow AI_HOME to be set
# after this module is imported.
_ai_router_loaded = False
_AI_ROUTER = False
_query_ai = None  # type: ignore[assignment]


def _ensure_ai_router() -> None:
    """Attempt to import ai_router once; result is cached globally."""
    global _ai_router_loaded, _AI_ROUTER, _query_ai
    if _ai_router_loaded:
        return
    _ai_router_loaded = True
    try:
        import pathlib as _pathlib
        import sys as _sys

        _ai_home = _pathlib.Path(
            os.environ.get("AI_HOME", str(_pathlib.Path.home() / ".ai-employee"))
        )
        _router_path = str(_ai_home / "agents" / "ai-router")
        if _router_path not in _sys.path:
            _sys.path.insert(0, _router_path)
        from ai_router import query_ai_for_agent as _qai  # type: ignore

        _AI_ROUTER = True
        _query_ai = _qai
    except ImportError:
        _AI_ROUTER = False
        _query_ai = None


def _ollama_post(endpoint: str, payload: dict, timeout: int) -> dict:
    """POST to the Ollama API and return parsed JSON."""
    url = f"{OLLAMA_HOST.rstrip('/')}/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA_HOST}: {exc}") from exc


# ── Lifecycle/quant gate (WS8b) ──────────────────────────────────────────────
# Per-model real GGUF quant, cached so we hit /api/show once per model.
_quant_cache: dict[str, str | None] = {}


def _ollama_quant(model: str) -> str | None:
    """Real GGUF quant of an installed model via /api/show (cached per-model)."""
    if model in _quant_cache:
        return _quant_cache[model]
    quant = None
    try:
        info = _ollama_post("/api/show", {"name": model}, 10)
        quant = (info.get("details") or {}).get("quantization_level")
    except Exception:  # noqa: BLE001
        quant = None
    _quant_cache[model] = quant
    return quant


def _legacy_offload_options(model: str) -> dict:
    """Fallback offload options via turbo_quant (used when a model has no vram_budget
    quant profile). Computes num_gpu/low_vram from disk_offload_config() + free VRAM —
    stops OOM on models exceeding VRAM (e.g. 14B on 8 GB)."""
    try:
        from neural_brain.models.lifecycle_manager import _free_vram_mb
        import importlib, pathlib as _pl, sys as _sys
        _tq_path = str(_pl.Path(__file__).parents[2] / "agents" / "turbo-quant")
        if _tq_path not in _sys.path:
            _sys.path.insert(0, _tq_path)
        _tq = importlib.import_module("turbo_quant")
        disk_offload_config = _tq.disk_offload_config
        select_quant = _tq.select_quant

        free_mb = _free_vram_mb()
        params_b = _MODEL_PARAMS_B.get(model, 0.0)
        # Fallback: strip tag and retry
        if params_b == 0.0:
            base = model.split(":")[0]
            params_b = _MODEL_PARAMS_B.get(base, 0.0)

        if params_b <= 0.0:
            # Unknown model — use safe defaults
            return {
                "num_thread": min(8, os.cpu_count() or 4),
                "num_batch": 256 if (free_mb or 0) < 4000 else 512,
            }

        quant = select_quant()
        cfg = disk_offload_config(params_b, quant)

        # RAM pressure check — offloaded layers live in RAM, so check available RAM too.
        # If system RAM < 3 GB free, cap GPU offload to avoid paging to disk.
        import psutil
        try:
            ram_free_gb = psutil.virtual_memory().available / (1024 ** 3)
        except Exception:  # noqa: BLE001
            ram_free_gb = 999.0  # unknown → no restriction
        ram_constrained = ram_free_gb < 3.0

        gpu_layers = cfg.get("gpu_layers_suggested", 0)
        # Under RAM pressure, prefer keeping more layers on GPU (less CPU offload work).
        if ram_constrained and gpu_layers > 0:
            total_layers = max(1, int(params_b * 4))  # ~4 layers per B param
            gpu_layers = min(total_layers, gpu_layers + max(2, int(total_layers * 0.1)))

        opts: dict = {
            "num_thread": min(8, os.cpu_count() or 4),
            "num_batch": 256 if (free_mb or 0) < 4000 else 512,
            "num_gpu": gpu_layers,
        }

        if free_mb is not None and free_mb < 2000:
            opts["low_vram"] = True

        logger.debug(
            "ollama_options model=%s params_b=%.1f quant=%s gpu_layers=%s free_mb=%s low_vram=%s",
            model, params_b, quant, gpu_layers, free_mb, opts.get("low_vram"),
        )
        return opts

    except Exception as exc:  # noqa: BLE001
        logger.debug("_legacy_offload_options skipped: %s", exc)
        return {}


def _build_ollama_options(model: str, quant: str | None = None) -> tuple[dict, dict]:
    """Ollama inference options + budget meta for ``model@quant`` (A4).

    Primary path: ``vram_budget.plan()`` — KV-cache-aware, measured free VRAM →
    num_gpu / num_ctx / low_vram. Fallback: legacy turbo_quant offload (unprofiled
    model). Returns ``(ollama_options, meta)``; meta carries est_vram_mb / free_vram_mb
    / num_gpu / num_ctx / fits / source for inference logging + lifecycle eviction (A6).
    """
    ctx = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
    n_thread = min(8, os.cpu_count() or 4)
    meta: dict = {"source": None, "num_ctx": ctx}
    try:
        from engine.compute.vram_budget import plan as _plan
        p = _plan(model, quant, ctx)
        if p.get("weights_mb") is not None:  # model has a quant profile → budget it
            free = p.get("free_vram_mb")
            opts: dict = {
                "num_thread": n_thread,
                "num_batch": 256 if (free is not None and free < 4000) else 512,
                "num_ctx": int(p.get("num_ctx", ctx)),
            }
            ng = p.get("num_gpu")
            if isinstance(ng, int) and ng >= 0:   # -1 == all layers → let Ollama default
                opts["num_gpu"] = ng
            if p.get("low_vram"):
                opts["low_vram"] = True
            meta.update(source="vram_budget", est_vram_mb=p.get("est_vram_mb"),
                        free_vram_mb=free, num_gpu=ng, num_ctx=opts["num_ctx"],
                        fits=p.get("fits"), recommend_remote=p.get("recommend_remote"))
            logger.debug("ollama_options[budget] model=%s quant=%s %s", model, quant, p.get("reason"))
            return opts, meta
    except Exception as exc:  # noqa: BLE001
        logger.debug("_build_ollama_options budget path skipped: %s", exc)
    meta.update(source="legacy")
    return _legacy_offload_options(model), meta


# ── Quant resolution + honest availability (A4) ───────────────────────────────
def _resolve_quant_model(base_model: str) -> tuple[str, str | None]:
    """Resolve the router's chosen model to (model, quant) via its quant ladder +
    live free VRAM (A2). Never changes model identity — only adds the best-fitting
    quant. Falls back to (base_model, None) if model_lanes/profile is unavailable."""
    try:
        from core.model_lanes import best_quant_for_model
        res = best_quant_for_model(base_model)
        return res.get("model", base_model), res.get("quant")
    except Exception as exc:  # noqa: BLE001
        logger.debug("_resolve_quant_model fallback model=%s: %s", base_model, exc)
        return base_model, None


_tags_cache: dict[str, Any] = {"ts": 0.0, "tags": None}


def _installed_tags(ttl: float = 30.0) -> set[str] | None:
    """Installed Ollama tags (cached ``ttl`` s). None = list unavailable (don't block)."""
    import time as _t
    now = _t.time()
    if _tags_cache["tags"] is not None and (now - _tags_cache["ts"]) < ttl:
        return _tags_cache["tags"]
    try:
        resp = _ollama_get("/api/tags", timeout=8)
        tags = {m.get("name", "") for m in resp.get("models", []) if m.get("name")}
        tags |= {n.split(":")[0] for n in list(tags) if ":" in n}  # also bare names
        _tags_cache.update(ts=now, tags=tags)
        return tags
    except Exception as exc:  # noqa: BLE001
        logger.debug("installed_tags unavailable: %s", exc)
        return None


def ensure_model_available(model: str, quant: str | None = None) -> dict:
    """Honest availability check for an Ollama model tag — never a silent OOM/downgrade.

    Installed → available. Not installed → ``ollama pull`` only when OLLAMA_AUTO_PULL=1
    (a multi-GB pull must never block the hot path silently); else return
    ``available=False`` + ``install_suggestion`` so the caller blocks/escalates.
    """
    tags = _installed_tags()
    if tags is None:
        return {"available": True, "model": model, "quant": quant,
                "reason": "tag list unavailable; proceeding (Ollama errors if missing)"}
    if model in tags or model.split(":")[0] in tags:
        return {"available": True, "model": model, "quant": quant, "reason": "installed"}
    if os.environ.get("OLLAMA_AUTO_PULL") == "1":
        try:
            logger.info("auto-pull model=%s (OLLAMA_AUTO_PULL=1)", model)
            _ollama_post("/api/pull", {"name": model, "stream": False}, 1800)
            _tags_cache["tags"] = None  # invalidate cache
            return {"available": True, "model": model, "quant": quant, "reason": "pulled"}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "model": model, "quant": quant,
                    "reason": f"auto-pull failed: {exc}", "install_suggestion": model}
    return {"available": False, "model": model, "quant": quant,
            "reason": f"model '{model}' not installed", "install_suggestion": model}


def _log_inference(model: str, quant: str | None, meta: dict, latency_ms: float, tier: str) -> None:
    """Append one inference record to ``state/turbo_quant.log.jsonl`` (A4 observability)."""
    try:
        import time as _t
        from core.state_paths import canonical_state_dir
        rec = {
            "ts": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
            "model": model, "quant": quant, "tier": tier,
            "est_vram_mb": meta.get("est_vram_mb"), "free_vram_mb": meta.get("free_vram_mb"),
            "num_gpu": meta.get("num_gpu"), "num_ctx": meta.get("num_ctx"),
            "fits": meta.get("fits"), "source": meta.get("source"),
            "latency_ms": round(latency_ms, 1),
        }
        path = canonical_state_dir() / "turbo_quant.log.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("_log_inference skipped: %s", exc)


_CORE_MODELS = [DEFAULT_MODEL, DEFAULT_EMBED_MODEL]

# Approximate VRAM (MB) per model — used by ensure_model_ready to decide whether to evict.
_MODEL_VRAM_MB: dict[str, int] = {
    "llama3.2":             2000,
    "llama3.2:latest":      2000,
    "gemma3":               3300,
    "gemma3:latest":        3300,
    "qwen2.5:7b-instruct":  4700,
    "qwen2.5-coder:14b":    9000,
    "llava":                4700,
    "llava:latest":         4700,
    "nomic-embed-text":      300,
}
# Models that should stay resident forever (keep_alive=-1)
_PERMANENT_MODELS: frozenset[str] = frozenset({DEFAULT_MODEL, DEFAULT_EMBED_MODEL, "llama3.2", "llama3.2:latest", "nomic-embed-text"})


def _ollama_get(endpoint: str, timeout: int) -> dict:
    """GET the Ollama API and return parsed JSON."""
    url = f"{OLLAMA_HOST.rstrip('/')}/{endpoint.lstrip('/')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA_HOST}: {exc}") from exc


def _evict_idle_models(keep: frozenset[str] | None = None) -> None:
    """Unload non-permanent models from Ollama VRAM (keep_alive=0).

    Called before loading a heavy model when VRAM headroom is tight.
    Permanent models (llama3.2, nomic-embed-text) are never evicted.
    """
    keep_set = keep if keep is not None else _PERMANENT_MODELS
    try:
        resp = _ollama_get("/api/ps", timeout=8)
        for m in resp.get("models", []):
            name = m.get("name", "")
            if name and name not in keep_set:
                logger.info("evict_idle model=%s", name)
                _ollama_unloader(name)()
    except Exception as exc:
        logger.debug("evict_idle_models skipped: %s", exc)


def ensure_model_ready(model: str, needed_mb: float | None = None) -> bool:
    """Warm *model* into VRAM, evicting idle models first if headroom is tight (A6).

    ``needed_mb`` is the live KV-aware VRAM estimate from ``vram_budget.plan`` (passed
    by generate()); when absent we fall back to the static ``_MODEL_VRAM_MB`` table.
    Permanent models (llama3.2, nomic-embed-text) get keep_alive=-1 so Ollama never
    evicts them between calls — one heavy model at a time, core models stay hot.
    On-demand heavy models get keep_alive=300s. Returns True on success.
    """
    if not model:
        return False
    needed_mb = needed_mb if needed_mb is not None else _MODEL_VRAM_MB.get(model, 5000)
    try:
        from neural_brain.models.lifecycle_manager import _free_vram_mb
        free_mb = _free_vram_mb() or 0
        if needed_mb > free_mb * 0.85:
            logger.info("ensure_model_ready: low VRAM (%d MB free, need %d) — evicting idle models", free_mb, needed_mb)
            _evict_idle_models(keep=_PERMANENT_MODELS | {model})
    except Exception as exc:
        logger.debug("ensure_model_ready vram check skipped: %s", exc)

    keep_alive: int = -1 if model in _PERMANENT_MODELS else 300
    try:
        _ollama_post("/api/generate", {"model": model, "prompt": " ", "keep_alive": keep_alive, "stream": False}, 30)
        logger.info("model_ready model=%s keep_alive=%s", model, keep_alive)
        return True
    except Exception as exc:
        logger.debug("ensure_model_ready failed model=%s: %s", model, exc)
        return False


def _warm_targets() -> list[str]:
    """Embed model + the always-hot tier models (FAST/NORMAL), deduped.

    Tiers are resolved hardware-dynamically; if model_lanes is unavailable we fall
    back to the static core list so warmup never breaks startup.
    """
    targets = [DEFAULT_EMBED_MODEL]
    try:
        from core.model_lanes import hot_tier_models
        for m in hot_tier_models():
            if m not in targets:
                targets.append(m)
    except Exception as exc:  # noqa: BLE001
        logger.debug("warm_core_models: tier resolution unavailable: %s", exc)
        for m in _CORE_MODELS:
            if m not in targets:
                targets.append(m)
    return targets


def warm_core_models() -> None:
    """Send keep_alive=-1 to core/hot-lane models so Ollama never evicts them between calls."""
    for m in _warm_targets():
        try:
            _ollama_post("/api/generate", {"model": m, "prompt": " ", "keep_alive": -1, "stream": False}, 30)
            logger.info("model_warm model=%s keep_alive=-1", m)
        except Exception as exc:  # noqa: BLE001
            logger.debug("model_warm skipped model=%s: %s", m, exc)


def _ollama_unloader(model: str):
    """Callable that drops *model* from VRAM (keep_alive=0 forces an unload)."""
    def _unload():
        try:
            _ollama_post("/api/generate", {"model": model, "prompt": " ",
                                           "keep_alive": 0, "stream": False}, 15)
        except Exception:  # noqa: BLE001
            pass
    return _unload


def _enforce_lifecycle(model: str):
    """Register model + evict-to-fit if not already resident. Returns (mgr, was_loaded).

    Robust by design: any failure returns (None, False) and the caller proceeds —
    inference must never break because the lifecycle manager is unavailable. Does NOT
    take the global heavy lock on the hot path; only ensure_room when not resident.
    """
    try:
        from neural_brain.models.lifecycle_manager import get_lifecycle_manager
        mgr = get_lifecycle_manager()
        e = mgr.register(model, "LLM", "ollama", unloader=_ollama_unloader(model))
        if not e.loaded:
            if not os.environ.get("MODEL_FABRIC_DEV_OVERRIDE"):
                q = _ollama_quant(model)
                if q and ("f16" in q.lower() or "f32" in q.lower() or q.upper() in ("FP16", "FP32")):
                    logger.warning("llm model %s is full-precision (%s) — not quantised", model, q)
            mgr.ensure_room("LLM")
        return mgr, e.loaded
    except Exception as exc:  # noqa: BLE001
        logger.debug("lifecycle gate skipped: %s", exc)
        return None, False


def generate(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    context: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Generate a text completion.

    Tries ai_router first (if available), then falls back to direct Ollama.

    Args:
        prompt:  The user prompt.
        system:  System instruction for the model.
        context: Optional extra context prepended to the prompt.
        model:   Model name override (uses OLLAMA_MODEL env var by default).
        timeout: HTTP timeout in seconds.

    Returns:
        Generated text as a plain string.
    """
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    decision = _route_model(prompt=prompt, context=context, requested_model=model)
    chosen_model = decision.chosen_model
    logger.info(
        "llm_route tier=%s estimated_tokens=%s model=%s",
        decision.tier,
        decision.estimated_tokens,
        chosen_model,
    )

    _ensure_ai_router()
    if _AI_ROUTER and _query_ai is not None:
        try:
            result: Any = _query_ai(
                agent_type="engine",
                prompt=full_prompt,
                system_prompt=system,
            )
            if isinstance(result, dict):
                # ai_router returns {"answer": "...", "provider": "...", "error": ...}
                if result.get("error") or not result.get("answer"):
                    raise RuntimeError(f"ai_router error: {result.get('error')}")
                return str(result["answer"])
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_router failed (%s) — falling back to direct Ollama", exc)

    # A4: resolve a concrete quant for the routed model + budget VRAM (KV-aware), and
    # fail honestly if the model isn't installed — never silently OOM or swap to a
    # weaker model. Model identity is unchanged; only the quant/offload plan is added.
    resolved_model, quant = _resolve_quant_model(chosen_model)
    avail = ensure_model_available(resolved_model, quant)
    if not avail.get("available", True):
        suggest = (f" — install: ollama pull {avail['install_suggestion']}"
                   if avail.get("install_suggestion") else "")
        raise RuntimeError(f"model '{resolved_model}' unavailable: {avail.get('reason')}{suggest}")

    offload_opts, budget = _build_ollama_options(resolved_model, quant)
    mgr, _ = _enforce_lifecycle(resolved_model)
    ensure_model_ready(resolved_model, needed_mb=budget.get("est_vram_mb"))
    payload = {
        "model": resolved_model,
        "prompt": full_prompt,
        "system": system,
        "stream": False,
        **({"options": offload_opts} if offload_opts else {}),
    }
    import time as _t
    t0 = _t.time()
    response = _ollama_post("/api/generate", payload, timeout)
    latency_ms = (_t.time() - t0) * 1000
    if mgr is not None:
        try:
            mgr.mark_loaded(resolved_model, load_ms=latency_ms, quant=_ollama_quant(resolved_model))
        except Exception:  # noqa: BLE001
            pass
    _log_inference(resolved_model, quant, budget, latency_ms, decision.tier)
    return response.get("response", "")


def embed(
    text: str,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]:
    """Return a vector embedding for *text* via Ollama.

    Args:
        text:    Input string to embed.
        model:   Embedding model name (uses OLLAMA_EMBED_MODEL env var by default).
        timeout: HTTP timeout in seconds.

    Returns:
        List of floats representing the embedding vector, or empty list on error.
    """
    chosen_model = model or DEFAULT_EMBED_MODEL
    try:
        payload = {"model": chosen_model, "prompt": text}
        response = _ollama_post("/api/embeddings", payload, timeout)
        return response.get("embedding", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed failed: %s", exc)
        return []

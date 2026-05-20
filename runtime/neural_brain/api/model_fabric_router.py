"""Model Fabric API — makes the 8 model architectures usable from one namespace.

Wraps the existing `ModelArchitectureRouter` (8 real backends) and the hardware-aware
`model_resolver` so every call uses a model that is actually installed and fits the host.
This is the public surface the UI talks to: per-capability endpoints + MoE auto-route +
hybrid RAG, all returning structured JSON with graceful fallbacks. No fake success states —
unavailable subsystems (e.g. LCM/SAM with no local backend) report `available: false`.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/model-fabric", tags=["model-fabric"])


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

# ── Cached hardware-aware resolution (re-resolved every 60s) ──────────────────
_resolved_cache: dict | None = None
_resolved_at: float = 0.0


def _resolved(force: bool = False) -> dict:
    global _resolved_cache, _resolved_at
    if force or _resolved_cache is None or (time.time() - _resolved_at) > 60:
        try:
            from neural_brain.models.model_resolver import resolve_models
            _resolved_cache = resolve_models()
        except Exception as e:  # noqa: BLE001
            logger.warning("model_resolver failed: %s", e)
            _resolved_cache = {"tier": "unknown", "hardware": {}, "installed": [], "resolved": {}}
        _resolved_at = time.time()
    return _resolved_cache


def _arch_model(arch: str) -> dict:
    """Resolved model entry for an architecture (or empty dict)."""
    return (_resolved().get("resolved") or {}).get(arch, {})


def _ollama_unloader(model: str):
    """Return a callable that drops an Ollama model from VRAM (keep_alive=0)."""
    def _unload():
        try:
            import ollama
            ollama.generate(model=model, prompt=" ", keep_alive=0, options={"num_predict": 1})
        except Exception:  # noqa: BLE001
            pass
    return _unload


def _register_unloader(arch: str, entry: dict):
    """Register a real unloader with the lifecycle manager for this arch's model."""
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager
    mgr = get_lifecycle_manager()
    model = entry.get("model")
    if not model:
        return mgr, None
    unloader = None
    if arch == "LCM":
        from neural_brain.models import lcm_backend
        unloader = lcm_backend.unload
    elif arch == "SAM":
        from neural_brain.models import sam_backend
        unloader = sam_backend.unload
    elif entry.get("provider") == "ollama":
        unloader = _ollama_unloader(model)
    mgr.register(model, arch, entry.get("provider", "ollama"), unloader=unloader)
    return mgr, model


def _route(arch: str, request: dict) -> dict:
    """Route through the existing router with VRAM-aware admission control.

    Heavy archs pass through the lifecycle manager: it serializes heavy loads,
    evicts idle heavy models to free VRAM, and — if even a full GPU can't hold the
    model — returns a structured 'needs remote compute' plan instead of OOM-crashing.
    """
    import time as _t
    from neural_brain.models.lifecycle_manager import HEAVY_ARCHS, get_lifecycle_manager
    from neural_brain.models.model_architecture_router import ModelArchitectureRouter
    entry = _arch_model(arch)
    if not entry.get("available", True):
        return {"status": "unavailable", "arch": arch, "reason": entry.get("reason", "unavailable"),
                "available": False}
    req = dict(request)
    if entry.get("model") and "model" not in req:
        req["model"] = entry["model"]
    if entry.get("provider") and "provider" not in req:
        req["provider"] = entry["provider"]

    mgr, model = _register_unloader(arch, entry)
    heavy = arch in HEAVY_ARCHS
    plan = None
    if heavy:
        plan = mgr.acquire_heavy(arch)
        if not plan.get("fits", True) and plan.get("recommend_remote"):
            mgr.release_heavy()
            return {"status": "needs_remote", "arch": arch, "model": model,
                    "available": True, "vram_plan": plan,
                    "reason": "model exceeds local VRAM — provision remote compute (Compute Fabric)"}
    try:
        t0 = _t.time()
        result = ModelArchitectureRouter.route(arch, req)
        if model and isinstance(result, dict) and result.get("status") in ("success", "ok"):
            mgr.mark_loaded(model, load_ms=(_t.time() - t0) * 1000)
        result.setdefault("arch", arch)
        result.setdefault("model", entry.get("model"))
        if plan and plan.get("evicted"):
            result["vram_evicted"] = plan["evicted"]
        return result
    finally:
        if heavy:
            mgr.release_heavy()


# ── MoE intent classifier (keyword-first; cheap, no model needed) ─────────────
_INTENT_RULES = [
    ("VLM", ("image", "screenshot", "photo", "picture", "what do you see", "analyze this image", "ui screenshot")),
    ("SAM", ("segment", "mask", "object detection", "ui region", "bounding box")),
    ("LCM", ("generate image", "draw ", "mockup", "visual concept", "render image", "create a picture")),
    ("LAM", ("run ", "execute", "perform action", "use tool", "call skill", "automate")),
    ("MLM", ("search memory", "recall", "retrieve from memory", "embed", "find documents", "semantic search")),
    ("SLM", ("classify", "label this", "quick", "one word", "short summary", "yes or no")),
]


def classify_intent(text: str) -> str:
    t = (text or "").lower()
    for arch, kws in _INTENT_RULES:
        if any(k in t for k in kws):
            return arch
    return "LLM"  # default: general reasoning/coding/planning


# ── Schemas ───────────────────────────────────────────────────────────────────
class PromptReq(BaseModel):
    prompt: str = Field(..., description="Input prompt")
    max_tokens: int = Field(1024, ge=1, le=8192)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class RouteReq(PromptReq):
    arch: str | None = Field(None, description="Force an architecture; else auto (MoE)")


class VisionReq(PromptReq):
    images: list[str] = Field(..., description="base64 strings or file paths")


class ActionReq(BaseModel):
    skill: str = Field(..., description="Skill/tool name")
    args: dict = Field(default_factory=dict)
    dry_run: bool = Field(True, description="Plan only; do not execute side effects")


class RagQueryReq(BaseModel):
    query: str
    k: int = Field(5, ge=1, le=50)


class RagIngestReq(BaseModel):
    text: str | None = None
    file_path: str | None = None
    metadata: dict = Field(default_factory=dict)
    tenant_id: str = Field("default")


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/models")
def models():
    """Static registry + hardware-aware resolution + installed models."""
    from neural_brain.models.model_architecture_router import ModelArchitectureRouter
    r = _resolved()
    return {
        "tier": r.get("tier"),
        "hardware": r.get("hardware"),
        "installed": r.get("installed"),
        "resolved": r.get("resolved"),
        "registry": ModelArchitectureRouter.get_registry(),
    }


@router.get("/health")
def health():
    """Per-architecture availability + live metrics."""
    from neural_brain.models.model_architecture_router import ModelArchitectureRouter
    try:
        from neural_brain.models.performance_tracker import get_tracker
        metrics = get_tracker().summary() if hasattr(get_tracker(), "summary") else {}
    except Exception:
        metrics = {}
    r = _resolved()
    subsystems = []
    for arch in ModelArchitectureRouter.ARCHS:
        entry = (r.get("resolved") or {}).get(arch, {})
        subsystems.append({
            "arch": arch,
            "available": entry.get("available", False),
            "model": entry.get("model"),
            "provider": entry.get("provider"),
            "reason": entry.get("reason"),
            "metrics": metrics.get(arch, {}),
        })
    online = sum(1 for s in subsystems if s["available"])
    return {"status": "ok", "tier": r.get("tier"), "online": online,
            "total": len(subsystems), "subsystems": subsystems}


@router.get("/status")
def status():
    """Fast module-status summary (Phase 4 shape). Never triggers a model load."""
    t0 = time.time()
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager, _free_vram_mb
    from neural_brain.models.model_architecture_router import ModelArchitectureRouter
    r = _resolved()
    available = sum(1 for a in ModelArchitectureRouter.ARCHS
                    if (r.get("resolved") or {}).get(a, {}).get("available"))
    lc = get_lifecycle_manager().status()
    loaded = lc["models_loaded"]
    ready = available > 0
    module_status = "online" if ready and loaded else ("degraded" if ready else "offline")
    reason = None if loaded else "models load on demand (none resident yet)"
    return {
        "status": module_status, "module": "model_fabric", "ready": ready,
        "models_loaded": loaded, "models_available": available, "models_total": len(ModelArchitectureRouter.ARCHS),
        "free_vram_mb": _free_vram_mb(), "tier": r.get("tier"),
        "active_quant": get_lifecycle_manager().select_quant(7.0).get("quant"),
        "reason": reason, "response_ms": round((time.time() - t0) * 1000, 1),
        "timestamp": _now_iso(),
    }


@router.post("/route")
def route(req: RouteReq):
    """MoE auto-route: classify intent → architecture → dispatch with resolved model."""
    arch = req.arch or classify_intent(req.prompt)
    # MLM is retrieval, not generation — a memory/recall intent means RAG, not a raw embed call.
    if arch == "MLM":
        rag = rag_query(RagQueryReq(query=req.prompt, k=5))
        rag["routed_arch"] = arch
        rag["auto_routed"] = req.arch is None
        return rag
    payload = {"prompt": req.prompt, "max_tokens": req.max_tokens, "temperature": req.temperature}
    result = _route(arch, payload)
    result["routed_arch"] = arch
    result["auto_routed"] = req.arch is None
    return result


@router.post("/llm")
def llm(req: PromptReq):
    return _route("LLM", req.model_dump())


@router.post("/slm")
def slm(req: PromptReq):
    return _route("SLM", req.model_dump())


@router.post("/vision/analyze")
def vision_analyze(req: VisionReq):
    return _route("VLM", req.model_dump())


@router.post("/vision/segment")
def vision_segment(req: VisionReq):
    return _route("SAM", req.model_dump())


@router.post("/generate/visual")
def generate_visual(req: PromptReq):
    return _route("LCM", req.model_dump())


@router.post("/actions/execute")
def actions_execute(req: ActionReq):
    """LAM action — dry-run by default; real execution requires dry_run=false."""
    if req.dry_run:
        return {"status": "dry_run", "arch": "LAM", "skill": req.skill, "args": req.args,
                "note": "Dry-run: no side effects executed. Set dry_run=false to run."}
    return _route("LAM", {"skill": req.skill, "args": req.args})


@router.post("/rag/query")
def rag_query(req: RagQueryReq):
    """Hybrid RAG retrieval over the memory router (vector + knowledge), with citations."""
    try:
        from memory.memory_router import get_memory_router
        hits = get_memory_router().retrieve(req.query, top_k=req.k) or []
        results = []
        for h in hits:
            if isinstance(h, dict):
                results.append({
                    "text": h.get("text") or h.get("content") or "",
                    "score": h.get("score"),
                    "source": h.get("source") or h.get("lane") or "memory",
                    "citation": h.get("key") or h.get("id"),
                })
            else:
                results.append({"text": str(h), "source": "memory"})
        return {"status": "success", "query": req.query, "count": len(results), "results": results}
    except Exception as e:  # noqa: BLE001
        logger.warning("rag_query failed: %s", e)
        return {"status": "error", "error": str(e), "results": []}


# ── Lifecycle ──────────────────────────────────────────────────────────────────
@router.get("/lifecycle/status")
def lifecycle_status():
    """Loaded/registered models, VRAM, idle timers — never triggers a load."""
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager
    return {"status": "ok", **get_lifecycle_manager().status()}


@router.post("/models/{model_id:path}/unload")
def model_unload(model_id: str):
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager
    ok = get_lifecycle_manager().unload(model_id)
    return {"status": "ok" if ok else "noop", "model_id": model_id, "unloaded": ok}


@router.post("/models/unload-idle")
def models_unload_idle():
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager
    return {"status": "ok", "unloaded": get_lifecycle_manager().unload_idle()}


# ── Quantisation ───────────────────────────────────────────────────────────────
class QuantSelectReq(BaseModel):
    params_b: float = Field(7.0, description="Model size in billions of params")
    dev_override: bool = Field(False, description="Allow FP16/FP32 (blocked by default)")


@router.get("/quantization/status")
def quantization_status():
    """Active GPU budget + the quant the selector would pick for a 7B model now."""
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager, _free_vram_mb
    mgr = get_lifecycle_manager()
    return {"status": "ok", "free_vram_mb": _free_vram_mb(),
            "recommended_7b": mgr.select_quant(7.0),
            "policy": "FP16/FP32 local loads blocked unless dev_override; quant fit to free VRAM"}


@router.get("/quantization/available")
def quantization_available():
    from neural_brain.models.lifecycle_manager import _QUANT_LADDER
    return {"status": "ok", "quants": [
        {"quant": n, "bpw": bpw, "quality": q, "speed": s} for n, bpw, q, s in _QUANT_LADDER]}


@router.post("/quantization/select")
def quantization_select(req: QuantSelectReq):
    from neural_brain.models.lifecycle_manager import get_lifecycle_manager
    return {"status": "ok", **get_lifecycle_manager().select_quant(req.params_b, dev_override=req.dev_override)}


@router.post("/rag/ingest")
def rag_ingest(req: RagIngestReq):
    """Ingest text or a file into memory for later retrieval."""
    try:
        if req.file_path:
            import asyncio
            from core.document_ingestion_pipeline import ingest_document
            result = asyncio.run(ingest_document(req.file_path, req.tenant_id))
            return {"status": "success", "mode": "file", **(result if isinstance(result, dict) else {})}
        if req.text:
            from memory.memory_router import get_memory_router
            get_memory_router().store(
                key=f"ingest-{int(time.time())}", text=req.text,
                memory_type="semantic", source="model-fabric/rag-ingest",
                importance=0.6, extra=req.metadata,
            )
            return {"status": "success", "mode": "text", "chars": len(req.text)}
        return {"status": "error", "error": "Provide text or file_path"}
    except Exception as e:  # noqa: BLE001
        logger.warning("rag_ingest failed: %s", e)
        return {"status": "error", "error": str(e)}

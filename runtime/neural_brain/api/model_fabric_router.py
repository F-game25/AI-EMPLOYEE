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


def _route(arch: str, request: dict) -> dict:
    """Route through the existing router, injecting the resolved model + provider."""
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
    result = ModelArchitectureRouter.route(arch, req)
    result.setdefault("arch", arch)
    result.setdefault("model", entry.get("model"))
    return result


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

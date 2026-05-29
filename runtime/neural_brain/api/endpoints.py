"""FastAPI endpoints for Neural Brain."""
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/neural-brain", tags=["neural-brain"])
logger = logging.getLogger(__name__)
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _server_error(operation: str) -> HTTPException:
    logger.warning("neural brain %s failed", operation)
    return HTTPException(status_code=500, detail=f"{operation} failed")

# Mount forge sub-router (lazy import to avoid circular issues at module load)
try:
    from neural_brain.forge.api import forge_router
    router.include_router(forge_router, prefix="")
except Exception:
    pass


# Request/response schemas
class ThinkRequest(BaseModel):
    input: str = Field(..., description="User query or task")
    user_id: str = Field(default="anonymous")
    thread_id: str | None = Field(None, description="Resume existing reasoning thread")
    force: bool = Field(False, description="Force deep reasoning")


class RecallRequest(BaseModel):
    query: str = Field(..., description="Memory query")
    k: int = Field(default=5, ge=1, le=50)
    types: list[str] | None = Field(None, description="Filter by memory types")
    user_id: str = Field(default="anonymous")


class RememberRequest(BaseModel):
    content: str = Field(..., description="Content to remember")
    type: str = Field(default="episodic", description="Memory type")
    user_id: str = Field(default="anonymous")
    metadata: dict | None = Field(None)


class ModelRouteRequest(BaseModel):
    arch: str = Field(..., description="Architecture: LLM|SLM|MoE|VLM|MLM|LAM|LCM|SAM")
    request: dict = Field(..., description="Backend-specific request")


# Endpoints
@router.post("/think")
async def think(req: ThinkRequest):
    """Run deep reasoning on user input."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        result = await get_engine().think_async(
            input_text=req.input,
            user_id=req.user_id,
            thread_id=req.thread_id,
        )
        return result
    except Exception:
        raise _server_error("think")


@router.post("/recall")
async def recall(req: RecallRequest):
    """Retrieve from long-term memory."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().recall(req.query, user_id=req.user_id, k=req.k)
    except Exception:
        raise _server_error("recall")


@router.post("/remember")
async def remember(req: RememberRequest):
    """Store in long-term memory."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().remember(req.content, memory_type=req.type, user_id=req.user_id, metadata=req.metadata)
    except Exception:
        raise _server_error("remember")


@router.delete("/forget/{memory_id}")
async def forget(memory_id: str):
    """Remove memory."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forget(memory_id)
    except Exception:
        raise _server_error("forget")


@router.get("/graph")
async def get_graph(depth: int = Query(2, ge=1, le=5), limit: int = Query(200, ge=10, le=1000)):
    """Fetch knowledge graph snapshot."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().get_graph_snapshot(limit=limit)
    except Exception:
        raise _server_error("graph snapshot")


@router.get("/graph/snapshot")
async def get_graph_snapshot(limit: int = Query(200, ge=10, le=1000)):
    """Alias for /graph — returns the full graph snapshot for dashboard use."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().get_graph_snapshot(limit=limit)
    except Exception:
        raise _server_error("graph snapshot")


@router.get("/graph/views/{view}")
async def get_graph_view(view: str, limit: int = Query(300, ge=10, le=1000)):
    """One of the four living memory graphs: shortterm|longterm|relations|unified."""
    try:
        from neural_brain.graph.memory_graphs import build_view
        return build_view(view, limit=limit)
    except Exception:  # noqa: BLE001
        raise _server_error("graph view")


@router.get("/threads")
async def list_threads(limit: int = Query(20, ge=1, le=200)):
    """List recent reasoning threads from trace JSONL files."""
    try:
        traces_dir = Path("state/neural_brain/traces")
        if not traces_dir.exists():
            return {"threads": []}
        threads = []
        for f in sorted(traces_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            thread_id = f.stem
            last_node = None
            try:
                with open(f) as fp:
                    lines = [l for l in fp if l.strip()]
                if lines:
                    last = json.loads(lines[-1])
                    last_node = last.get("node")
            except Exception:
                pass
            threads.append({"thread_id": thread_id, "last_node": last_node, "ts": f.stat().st_mtime})
        return {"threads": threads}
    except Exception:
        raise _server_error("threads list")


@router.post("/models/route")
async def route_model(req: ModelRouteRequest):
    """Route request to specified architecture."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().route_model(req.arch, req.request)
    except Exception:
        raise _server_error("model route")


@router.get("/models/status")
async def get_model_status():
    """Live performance stats per architecture."""
    try:
        from neural_brain.models.performance_tracker import get_tracker
        tracker = get_tracker()
        archs = ["LLM", "SLM", "MoE", "VLM", "MLM", "LAM", "LCM", "SAM"]
        return {arch: tracker.get_all_stats(arch) for arch in archs}
    except Exception:
        raise _server_error("model status")


@router.get("/models/registry")
async def get_registry():
    """Fetch model registry."""
    try:
        from neural_brain.models.model_architecture_router import ModelArchitectureRouter
        return ModelArchitectureRouter.get_registry()
    except Exception:
        raise _server_error("model registry")


@router.get("/status")
async def get_status():
    """System health and readiness."""
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().get_status()
    except Exception:
        raise _server_error("status")


@router.get("/reasoning/{trace_id}")
async def get_reasoning_trace(trace_id: str):
    """Retrieve full reasoning trace."""
    try:
        if not _SAFE_TRACE_ID.fullmatch(trace_id):
            raise HTTPException(status_code=400, detail="Invalid trace id")
        trace_root = os.path.realpath("state/neural_brain/traces")
        trace_file = os.path.realpath(os.path.join(trace_root, f"{trace_id}.jsonl"))
        if os.path.commonpath([trace_root, trace_file]) != trace_root:
            raise HTTPException(status_code=400, detail="Invalid trace path")
        trace_file = Path(trace_file)
        if not trace_file.exists():
            raise HTTPException(status_code=404, detail="Trace not found")
        traces = []
        with open(trace_file) as f:
            for line in f:
                if line.strip():
                    traces.append(json.loads(line))
        return {"thread_id": trace_id, "traces": traces}
    except HTTPException:
        raise
    except Exception:
        raise _server_error("reasoning trace")

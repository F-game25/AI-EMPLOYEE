"""FastAPI endpoints for Neural Brain."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/neural-brain", tags=["neural-brain"])


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
async def think(req: ThinkRequest, request=None):
    """Run deep reasoning on user input."""
    try:
        from neural_brain.core.consciousness_engine import ConsciousnessEngine

        engine = ConsciousnessEngine()
        result = engine.think(
            input_text=req.input,
            user_id=req.user_id,
            thread_id=req.thread_id,
            force=req.force,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recall")
async def recall(req: RecallRequest):
    """Retrieve from long-term memory."""
    try:
        from neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        mem = NeuralMemoryManager()
        result = mem.recall(req.query, k=req.k)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remember")
async def remember(req: RememberRequest):
    """Store in long-term memory."""
    try:
        from neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        mem = NeuralMemoryManager()
        result = mem.remember(
            content=req.content,
            type=req.type,
            user_id=req.user_id,
            metadata=req.metadata or {},
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/forget/{memory_id}")
async def forget(memory_id: str):
    """Remove memory."""
    try:
        from neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        mem = NeuralMemoryManager()
        mem.forget(memory_id)
        return {"id": memory_id, "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph")
async def get_graph(depth: int = Query(2, ge=1, le=5), limit: int = Query(200, ge=10, le=1000)):
    """Fetch knowledge graph snapshot."""
    try:
        from neural_brain.core.consciousness_engine import ConsciousnessEngine

        engine = ConsciousnessEngine()
        return engine.get_graph_snapshot(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/route")
async def route_model(req: ModelRouteRequest):
    """Route request to specified architecture."""
    try:
        from neural_brain.models.model_architecture_router import ModelArchitectureRouter

        result = ModelArchitectureRouter.route(req.arch, req.request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/registry")
async def get_registry():
    """Fetch model registry."""
    try:
        from neural_brain.models.model_architecture_router import ModelArchitectureRouter

        return ModelArchitectureRouter.get_registry()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """System health and readiness."""
    try:
        from neural_brain.core.consciousness_engine import ConsciousnessEngine

        engine = ConsciousnessEngine()
        return engine.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reasoning/{trace_id}")
async def get_reasoning_trace(trace_id: str):
    """Retrieve full reasoning trace."""
    try:
        from pathlib import Path
        import json

        trace_file = Path("state/neural_brain/traces") / f"{trace_id}.jsonl"
        if not trace_file.exists():
            raise HTTPException(status_code=404, detail="Trace not found")

        traces = []
        with open(trace_file) as f:
            for line in f:
                traces.append(json.loads(line))

        return {"thread_id": trace_id, "traces": traces}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

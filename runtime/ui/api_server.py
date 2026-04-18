"""AI Employee UI API Server — FastAPI backend for the dashboard.

Provides REST endpoints consumed by the Streamlit dashboard and any
external integrations.  Runs on port ``AI_EMPLOYEE_UI_API_PORT``
(default 7890) on loopback only.

Endpoints
---------
GET  /health                  — liveness probe
GET  /status                  — system-wide status summary
GET  /brain/metrics           — self-learning brain metrics + recent outcomes
GET  /agents                  — list of known agents and their success rates
GET  /memory                  — memory health (cache + vector counts)
POST /memory/search           — semantic search across all memory
POST /memory/store            — write a new memory entry via the router
POST /brain/record_outcome    — record an agent outcome for reinforcement

Launching
---------
This module can be run directly::

    python -m ui.api_server

or imported and launched programmatically::

    from ui.api_server import start_api_server
    start_api_server()   # blocks; call in a thread for background use
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("ui.api_server")

# ── Ensure runtime/ is on sys.path when this file is run directly ─────────────

_HERE = Path(__file__).resolve()
_RUNTIME = _HERE.parents[1]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

# ── FastAPI (optional — informative error if missing) ─────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    FastAPI = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]

_API_PORT = int(os.environ.get("AI_EMPLOYEE_UI_API_PORT", "7890"))
_API_HOST = os.environ.get("AI_EMPLOYEE_UI_API_HOST", "127.0.0.1")


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_app() -> Any:
    """Build and return the FastAPI application instance."""
    if not _HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required to run the UI API server. "
            "Install it with: pip install fastapi uvicorn"
        )

    from core.self_learning_brain import get_self_learning_brain
    from memory.memory_router import get_memory_router

    app = FastAPI(
        title="AI Employee — UI API",
        version="1.0.0",
        description="Internal REST API for the AI Employee dashboard.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ── Models ────────────────────────────────────────────────────────────────

    class MemorySearchRequest(BaseModel):
        query: str
        memory_type: str | None = None
        top_k: int = 5

    class MemoryStoreRequest(BaseModel):
        key: str
        text: str
        memory_type: str = "semantic"
        source: str = ""
        importance: float = 0.5
        agent: str = ""

    class OutcomeRequest(BaseModel):
        action: str
        success: bool
        context: str = ""
        strategy: str = "default"
        duration_ms: int = 0

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "ts": _ts()}

    @app.get("/status")
    def status() -> dict:
        try:
            router = get_memory_router()
            brain = get_self_learning_brain()
            mem_health = router.health()
            metrics = brain.metrics()
            return {
                "status": "ok",
                "brain": {
                    "avg_reward": metrics.get("avg_reward_recent", 0.0),
                    "total_outcomes": metrics.get("total_outcomes_recorded", 0),
                },
                "memory": mem_health,
                "ts": _ts(),
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/brain/metrics")
    def brain_metrics() -> dict:
        try:
            brain = get_self_learning_brain()
            return {
                **brain.metrics(),
                "recent_outcomes": brain.recent_outcomes(limit=20),
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/agents")
    def list_agents() -> dict:
        try:
            import core.brain_model as _bm
            from core.learning_engine import LearningEngine

            le = LearningEngine()
            model = _bm.get_agent_model()
            agents = []
            for name, weights in model.items():
                agents.append({
                    "name": name,
                    "success_rate": round(le.agent_success_rate(name), 3),
                    "weights": {k: round(v, 3) for k, v in weights.items()},
                })
            return {"agents": agents, "count": len(agents), "ts": _ts()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/memory")
    def memory_health() -> dict:
        try:
            return get_memory_router().health()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/memory/search")
    def memory_search(req: MemorySearchRequest) -> dict:
        try:
            results = get_memory_router().retrieve(
                req.query,
                memory_type=req.memory_type,
                top_k=req.top_k,
            )
            return {"results": results, "count": len(results), "ts": _ts()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/memory/store")
    def memory_store(req: MemoryStoreRequest) -> dict:
        try:
            result = get_memory_router().store(
                req.key,
                req.text,
                memory_type=req.memory_type,
                source=req.source,
                importance=req.importance,
                agent=req.agent,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/brain/record_outcome")
    def record_outcome(req: OutcomeRequest) -> dict:
        try:
            result = get_self_learning_brain().record_outcome(
                action=req.action,
                success=req.success,
                context=req.context,
                strategy=req.strategy,
                duration_ms=req.duration_ms,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Ascend Forge endpoints ─────────────────────────────────────────────────

    class ForgeSubmitRequest(BaseModel):
        module: str
        code: str
        description: str = ""
        tag: str = ""
        author: str = "api"
        auto_deploy: bool = False

    class ForgeApproveRequest(BaseModel):
        snapshot_id: str

    class ForgeRollbackRequest(BaseModel):
        snapshot_id: str

    class SandboxRunRequest(BaseModel):
        code: str
        module_name: str = "preview_module"
        target_module: str = ""

    @app.post("/forge/submit")
    def forge_submit(req: ForgeSubmitRequest) -> dict:
        try:
            from core.forge_controller import get_forge_controller
            return get_forge_controller().submit_change(
                module=req.module,
                code=req.code,
                description=req.description,
                tag=req.tag,
                author=req.author,
                auto_deploy=req.auto_deploy,
            )
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Forge submit failed — check server logs") from None

    @app.post("/forge/approve")
    def forge_approve(req: ForgeApproveRequest) -> dict:
        try:
            from core.forge_controller import get_forge_controller
            return get_forge_controller().approve(req.snapshot_id)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Forge approve failed — check server logs") from None

    @app.post("/forge/rollback")
    def forge_rollback(req: ForgeRollbackRequest) -> dict:
        try:
            from core.forge_controller import get_forge_controller
            return get_forge_controller().rollback(req.snapshot_id)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Forge rollback failed — check server logs") from None

    @app.get("/forge/pending")
    def forge_pending() -> dict:
        try:
            from core.forge_controller import get_forge_controller
            return {"pending": get_forge_controller().list_pending(), "ts": _ts()}
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Forge pending query failed — check server logs") from None

    @app.get("/forge/versions")
    def forge_versions(module: str | None = None, limit: int = 50) -> dict:
        try:
            from runtime.runtime.version_control import get_version_control
            return {
                "versions": get_version_control().list_versions(module=module, limit=limit),
                "summary": get_version_control().summary(),
                "ts": _ts(),
            }
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Version query failed — check server logs") from None

    @app.post("/forge/sandbox")
    def forge_sandbox(req: SandboxRunRequest) -> dict:
        try:
            from runtime.sandbox_executor import get_sandbox_executor
            return get_sandbox_executor().run(
                req.code,
                module_name=req.module_name,
                target_module=req.target_module,
            )
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Sandbox execution failed — check server logs") from None

    return app


# ── Singleton app (lazy) ──────────────────────────────────────────────────────

_app: Any = None
_app_lock = threading.Lock()


def get_app() -> Any:
    """Return the FastAPI application (built once on first call)."""
    global _app
    with _app_lock:
        if _app is None:
            _app = _build_app()
    return _app


# ── Launcher ──────────────────────────────────────────────────────────────────

def start_api_server(
    *,
    host: str = _API_HOST,
    port: int = _API_PORT,
    log_level: str = "warning",
) -> None:
    """Start the Uvicorn server.  **Blocks the calling thread.**"""
    try:
        import uvicorn  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "uvicorn is required to run the UI API server. "
            "Install it with: pip install uvicorn"
        ) from exc

    app = get_app()
    logger.info("Starting UI API server (see AI_EMPLOYEE_UI_API_PORT / AI_EMPLOYEE_UI_API_HOST)")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


def start_api_server_thread(
    *,
    host: str = _API_HOST,
    port: int = _API_PORT,
) -> threading.Thread:
    """Start the API server in a daemon background thread.

    Returns:
        The started thread (daemon=True; stops when the main process exits).
    """
    t = threading.Thread(
        target=start_api_server,
        kwargs={"host": host, "port": port},
        name="ui-api-server",
        daemon=True,
    )
    t.start()
    logger.info("UI API server thread started (see AI_EMPLOYEE_UI_API_PORT / AI_EMPLOYEE_UI_API_HOST)")
    return t


# ── Direct execution ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ui.api_server] %(levelname)s — %(message)s",
    )
    start_api_server()

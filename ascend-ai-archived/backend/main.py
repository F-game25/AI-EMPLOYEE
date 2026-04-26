"""
ASCEND AI — Main Application
Single backend on port 8787.
UI loads independently — dashboard works even when ALL agents are offline.
"""

import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from routers.agents import router as agents_router
from routers.ascend_forge import router as forge_router
from routers.blacklight import router as blacklight_router
from routers.chat import router as chat_router
from routers.doctor import router as doctor_router
from routers.fairness import router as fairness_router
from routers.governance import router as governance_router
from routers.hermes import router as hermes_router
from routers.memory import router as memory_router
from routers.money_mode import router as money_router
from routers.settings import router as settings_router
from routers.system import router as system_router
from websocket_manager import (
    agents_broadcast_loop,
    router as ws_router,
    stats_broadcast_loop,
)

app = FastAPI(
    title="ASCEND AI",
    version="1.0.0",
    description="Autonomous multi-agent business assistant",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers (all under /api prefix) ──────────────────────────────
app.include_router(agents_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(forge_router, prefix="/api")
app.include_router(money_router, prefix="/api")
app.include_router(blacklight_router, prefix="/api")
app.include_router(doctor_router, prefix="/api")
app.include_router(hermes_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(fairness_router, prefix="/api")
app.include_router(governance_router, prefix="/api")

# ── WebSocket ────────────────────────────────────────────────────────
app.include_router(ws_router)

# ── Serve React build (LAST — after all API routes) ─────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    # Mount static assets (JS/CSS) under /assets
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA catch-all: every non-API path returns index.html
    _index_html = os.path.join(static_dir, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(_index_html)


# ── Startup ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    startup_results: dict[str, str] = {}

    # Start LLM router (Ollama ping + background health check)
    try:
        from services.llm_router import get_llm_router

        await get_llm_router().startup()
        status = get_llm_router().get_status()
        startup_results["llm_router"] = (
            f"OK — provider={status['provider']} model={status['model']}"
        )
    except Exception as e:
        logger.error("[STARTUP] llm_router failed: %s", e)
        startup_results["llm_router"] = f"FAILED: {e}"

    # Start system monitor background polling
    try:
        from services.system_monitor import poll_forever

        asyncio.create_task(poll_forever())
        startup_results["system_monitor"] = "OK"
    except Exception as e:
        logger.error("[STARTUP] system_monitor failed: %s", e)
        startup_results["system_monitor"] = f"FAILED: {e}"

    # Initialise agent manager
    try:
        from services.agent_manager import startup as agent_startup

        await agent_startup()
        startup_results["agent_manager"] = "OK"
    except Exception as e:
        logger.error("[STARTUP] agent_manager failed: %s", e)
        startup_results["agent_manager"] = f"FAILED: {e}"

    # Start WebSocket broadcast loops
    try:
        asyncio.create_task(stats_broadcast_loop())
        asyncio.create_task(agents_broadcast_loop())
        startup_results["ws_broadcast_loops"] = "OK"
    except Exception as e:
        logger.error("[STARTUP] ws_broadcast_loops failed: %s", e)
        startup_results["ws_broadcast_loops"] = f"FAILED: {e}"

    # Start log streamer
    try:
        from services.log_streamer import tail_logs_forever
        from websocket_manager import broadcast

        asyncio.create_task(tail_logs_forever(broadcast))
        startup_results["log_streamer"] = "OK"
    except Exception as e:
        logger.error("[STARTUP] log_streamer failed: %s", e)
        startup_results["log_streamer"] = f"FAILED: {e}"

    # ── Startup summary ────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("ASCEND AI STARTUP SUMMARY")
    for subsystem, result in startup_results.items():
        level = "✓" if result.startswith("OK") else "✗"
        logger.info("  %s %-22s %s", level, subsystem, result)
    logger.info("=" * 60)


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8787)

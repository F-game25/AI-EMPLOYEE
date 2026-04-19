"""
ASCEND AI — Main Application
Single backend on port 8787.
UI loads independently — dashboard works even when ALL agents are offline.
"""

import asyncio
import os

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.mock_layer import get_mock_health
from websocket_manager import manager

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


# ── Health endpoint ──────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return get_mock_health()


# ── WebSocket endpoint ───────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now; routers will add real handlers in Part 2
            await manager.send_personal(websocket, "echo", {"message": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Routers (stubs — populated in Part 2) ────────────────────────────
# from routers.agents import router as agents_router
# from routers.chat import router as chat_router
# from routers.system import router as system_router
# from routers.ascend_forge import router as forge_router
# from routers.money_mode import router as money_router
# from routers.blacklight import router as blacklight_router
# from routers.doctor import router as doctor_router
#
# app.include_router(agents_router, prefix="/api")
# app.include_router(chat_router, prefix="/api")
# app.include_router(system_router, prefix="/api")
# app.include_router(forge_router, prefix="/api")
# app.include_router(money_router, prefix="/api")
# app.include_router(blacklight_router, prefix="/api")
# app.include_router(doctor_router, prefix="/api")


# ── Serve React build (LAST — after all API routes) ─────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# ── Startup ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    # Start system monitor background polling
    try:
        from services.system_monitor import poll_forever

        asyncio.create_task(poll_forever())
    except Exception:
        pass  # Never crash if monitor fails

    # Initialise agent manager
    try:
        from services.agent_manager import startup as agent_startup

        await agent_startup()
    except Exception:
        pass  # Never crash if agents are broken


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8787)

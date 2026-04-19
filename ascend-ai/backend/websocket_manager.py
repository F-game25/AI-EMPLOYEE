"""
ASCEND AI — WebSocket Manager
Manages connected WebSocket clients, broadcasts system stats and agent status.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
_clients: list[WebSocket] = []


async def broadcast(message: dict):
    """Send a JSON message to every connected WebSocket client."""
    dead: list[WebSocket] = []
    for ws in _clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        if websocket in _clients:
            _clients.remove(websocket)


async def stats_broadcast_loop():
    """Push system stats to all connected clients every 2 seconds."""
    from services.system_monitor import get_stats

    while True:
        await broadcast({"type": "system_stats", "data": get_stats()})
        await asyncio.sleep(2)


async def agents_broadcast_loop():
    """Push agent status to all connected clients every 10 seconds."""
    from services.agent_manager import get_all_statuses

    while True:
        await broadcast({"type": "agent_status", "data": get_all_statuses()})
        await asyncio.sleep(10)

"""
ASCEND AI — WebSocket Manager
Manages connected WebSocket clients, broadcasts system stats and agent status.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)
_clients: list[WebSocket] = []

# ── Short-lived chunk buffer (Break #6) ─────────────────────────────
# Stores (timestamp, message) for chat_chunk messages broadcast when no
# clients are connected. Flushed to the next connecting client.
_BUFFER_MAX = 100
_BUFFER_TTL = 30.0  # seconds
_chunk_buffer: list[tuple[float, dict]] = []


async def broadcast(message: dict):
    """Send a JSON message to every connected WebSocket client.

    If no clients are connected and the message is a ``chat_chunk``, it is
    stored in the short-lived buffer so it can be delivered when a client
    reconnects within 30 seconds.
    """
    if not _clients:
        if message.get("type") == "chat_chunk":
            logger.warning(
                "broadcast: no clients connected, buffering chat_chunk (buffer=%d)",
                len(_chunk_buffer),
            )
            if len(_chunk_buffer) < _BUFFER_MAX:
                _chunk_buffer.append((time.monotonic(), message))
        return

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

    # Flush any buffered chunks to this newly-connected client (Break #6)
    now = time.monotonic()
    fresh = [(ts, msg) for ts, msg in _chunk_buffer if now - ts < _BUFFER_TTL]
    _chunk_buffer.clear()
    if fresh:
        logger.info(
            "websocket_endpoint: flushing %d buffered chunk(s) to new client",
            len(fresh),
        )
    for _ts, msg in fresh:
        try:
            await websocket.send_json(msg)
        except Exception:
            break

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

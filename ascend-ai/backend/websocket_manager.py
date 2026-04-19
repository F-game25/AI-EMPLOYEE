"""
ASCEND AI — WebSocket Manager
Manages connected WebSocket clients and broadcasts messages.
"""

import json
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """Keeps track of active WebSocket connections and broadcasts to all."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: str, data: Any = None):
        """Send a JSON message to every connected client."""
        message = json.dumps({"event": event, "data": data})
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, event: str, data: Any = None):
        """Send a JSON message to a single client."""
        message = json.dumps({"event": event, "data": data})
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)


manager = WebSocketManager()

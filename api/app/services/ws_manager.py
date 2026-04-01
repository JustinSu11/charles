"""
ws_manager.py — WebSocket connection manager.

Maintains the set of active browser connections and broadcasts JSON payloads
to all of them.  Import the module-level `manager` singleton everywhere you
need to broadcast (e.g. from chat.py after a turn completes).

Single-process safe: all connections live in one asyncio event loop so the
plain list never has concurrency issues.
"""

import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WS client connected  (total: %d)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info("WS client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, payload: dict) -> None:
        """Send *payload* as JSON text to every connected browser."""
        text = json.dumps(payload, default=str)  # default=str handles UUIDs / datetimes
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


# Module-level singleton — import this everywhere
manager = ConnectionManager()

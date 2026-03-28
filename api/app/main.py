import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import ping_db
from app.routers import chat, history, openai_compat
from app.services.ws_manager import manager

# Resolve path to the static directory relative to this file
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="Charles API",
    description="Core API for the Charles AI assistant - handles chat, history, and OpenRouter integration.",
    version="1.0.0",
)

# CORS — allow the voice service and any local browser tab to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",  # Custom web UI (served by this API)
        "http://localhost:8001",  # Voice service
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(history.router)
app.include_router(openai_compat.router)

# Serve static assets (CSS, JS if we ever split them out)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ── Web UI ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the single-page chat UI."""
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time broadcast channel.
    The browser connects here on load.  After every chat turn (voice or web),
    chat.py calls manager.broadcast() so all connected clients see new messages
    the moment they're stored — no polling required.
    """
    await manager.connect(websocket)
    try:
        while True:
            # We don't use client→server WS messages, but we must receive
            # to detect disconnects and keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    Returns API status and whether PostgreSQL is reachable.
    Used by Docker healthcheck and the GUI launcher status indicator.
    """
    db_status = await ping_db()
    return {
        "status": "ok",
        "database": "reachable" if db_status else "unreachable",
    }

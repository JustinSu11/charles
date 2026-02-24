from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import ping_db
from app.routers import chat, history

app = FastAPI(
    title = "Charles API",
    description = "Core API for the Charles AI assistant - handles chat, history, and OpenRouter integration.",
    version="1.0.0",
)

# CORS

# Allow Open WebUI (port 3000) and the voice service (port 8001) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", # OpenWebUI
        "http://localhost:8001", # Voice Service
        "http://127.0.1:3000",
        "http://127.0.1:8001",
    ],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(history.router)

# Health check
@app.get("/health")
async def health():
    """
    Returns API status and whether PostgreSQL is reachable.
    Used by Docker healthcheck and the GUI launcher status indicator.
    """
    db_status = await ping_db()
    return {
        "status": "ok", 
        "database": "reachable" if db_status else "unreachable"
    }
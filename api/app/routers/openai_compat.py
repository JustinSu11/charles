"""
OpenAI-compatible API endpoints (/v1/models, /v1/chat/completions).

Allows Open WebUI to use Charles API as its LLM backend.
Charles proxies requests to OpenRouter, injecting the system prompt
and (in the future) storing conversation data in PostgreSQL.
"""

import time
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.openrouter import OPENROUTER_API_KEY, MODEL, SYSTEM_PROMPT

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _openrouter_headers() -> dict:
    """Common headers for every OpenRouter request."""
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Charles AI Assistant",
    }


# ── Models ────────────────────────────────────────────────────────────────


@router.get("/models")
async def list_models():
    """
    Proxy the model catalogue from OpenRouter so Open WebUI can
    populate its model selector with every available model.

    Falls back to a single-model list if OpenRouter is unreachable.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{OPENROUTER_BASE}/models",
                headers=_openrouter_headers(),
            )
            if resp.status_code == 200:
                return JSONResponse(content=resp.json())
    except httpx.RequestError:
        pass  # fall through to the fallback

    # Fallback: return at least the configured default model
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openrouter",
            }
        ],
    }


# ── Chat completions ─────────────────────────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.

    Open WebUI  →  Charles API (/v1/chat/completions)  →  OpenRouter
                                                        →  (stores in PG, future)

    Supports both streaming (SSE) and non-streaming responses.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # Inject Charles system prompt when the caller hasn't provided one
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    headers = _openrouter_headers()

    # Build the payload – forward the most commonly used parameters
    payload = {
        "model": body.get("model", MODEL),
        "messages": messages,
        "stream": stream,
    }
    for key in ("temperature", "max_tokens", "top_p",
                "frequency_penalty", "presence_penalty", "stop"):
        if key in body:
            payload[key] = body[key]

    if stream:
        return StreamingResponse(
            _stream_response(headers, payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # prevents Nginx from buffering SSE
            },
        )

    # ── Non-streaming ─────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=payload,
            headers=headers,
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


# ── Streaming helper ──────────────────────────────────────────────────────


async def _stream_response(headers: dict, payload: dict):
    """
    Open a streaming connection to OpenRouter and forward each SSE
    chunk back to the caller (Open WebUI) verbatim.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{OPENROUTER_BASE}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    yield f"{line}\n\n"

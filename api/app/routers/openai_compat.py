"""
OpenAI-compatible API endpoints (/v1/models, /v1/chat/completions).

Allows Open WebUI to use Charles API as its LLM backend.
Charles proxies requests to OpenRouter, injecting the system prompt
and (in the future) storing conversation data in PostgreSQL.
"""

import json
import time
import uuid
import httpx
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.openrouter import OPENROUTER_API_KEY, MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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


def _error_as_sse(message: str, model: str = "error") -> str:
    """
    Format an error as an OpenAI-compatible SSE chunk so Open WebUI
    displays it as assistant text instead of a cryptic parse failure.
    """
    chunk = {
        "id": f"chatcmpl-err-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": f"⚠️ {message}"},
                "finish_reason": "stop",
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


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
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json=payload,
                headers=headers,
            )

        data = resp.json()

        # OpenRouter returns errors with an "error" key — translate to
        # a proper OpenAI-shaped error so Open WebUI understands it.
        if resp.status_code != 200 or "error" in data:
            error_info = data.get("error", {})
            msg = error_info.get("message", "Unknown upstream error")
            code = error_info.get("code", resp.status_code)
            logger.warning("OpenRouter error (non-stream): %s %s", code, msg)
            return JSONResponse(
                status_code=resp.status_code if resp.status_code != 200 else 502,
                content={
                    "error": {
                        "message": msg,
                        "type": "upstream_error",
                        "code": str(code),
                    }
                },
            )

        return JSONResponse(content=data)

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenRouter timed out.")
    except httpx.RequestError as exc:
        logger.error("OpenRouter request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach OpenRouter.")


# ── Streaming helper ──────────────────────────────────────────────────────


async def _stream_response(headers: dict, payload: dict):
    """
    Open a streaming connection to OpenRouter and forward each SSE
    chunk back to the caller (Open WebUI) verbatim.

    If OpenRouter returns a non-2xx status (e.g. 429 rate limit),
    emit a single SSE error chunk so Open WebUI displays the error
    gracefully instead of failing with a cryptic "user not found".
    """
    model = payload.get("model", "unknown")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                # ── Handle upstream errors ────────────────────────────
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    try:
                        error_data = json.loads(error_body)
                        error_msg = (
                            error_data.get("error", {}).get("message")
                            or error_body.decode(errors="replace")
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        error_msg = error_body.decode(errors="replace")

                    logger.warning(
                        "OpenRouter error (stream): %s %s",
                        resp.status_code,
                        error_msg[:200],
                    )
                    yield _error_as_sse(
                        f"OpenRouter returned {resp.status_code}: {error_msg}",
                        model=model,
                    )
                    return

                # ── Normal streaming path ─────────────────────────────
                async for line in resp.aiter_lines():
                    if line.strip():
                        yield f"{line}\n\n"

    except httpx.TimeoutException:
        logger.error("OpenRouter stream timed out")
        yield _error_as_sse("OpenRouter timed out. Please try again.", model=model)
    except httpx.RequestError as exc:
        logger.error("OpenRouter stream connection error: %s", exc)
        yield _error_as_sse(
            "Could not connect to OpenRouter. Please try again.", model=model
        )

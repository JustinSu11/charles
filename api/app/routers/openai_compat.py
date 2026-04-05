"""
OpenAI-compatible API endpoints (/v1/models, /v1/chat/completions).

Allows Open WebUI to use Charles API as its LLM backend.  Charles proxies
requests to OpenRouter but uses PostgreSQL as the single source of truth for
conversation history so voice and web turns are always combined.
"""

import json
import time
import uuid
import httpx
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.services.openrouter import OPENROUTER_API_KEY, MODEL, BASE_SYSTEM_PROMPT as SYSTEM_PROMPT
from app.services.conversation import (
    get_or_create_shared_conversation,
    fetch_history,
    store_message,
)

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
async def chat_completions(request: Request, db: AsyncSession = Depends(get_db)):
    """
    OpenAI-compatible chat completions endpoint.

    Open WebUI  →  Charles API (/v1/chat/completions)  →  OpenRouter

    Uses PostgreSQL as the source of truth for history so voice and web
    conversations are always combined.  The messages sent by Open WebUI are
    used only to extract the latest user turn; everything else comes from DB.

    Supports both streaming (SSE) and non-streaming responses.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    body = await request.json()
    incoming_messages = body.get("messages", [])
    stream = body.get("stream", False)

    # Extract the last user message from what Open WebUI sent
    last_user_msg = next(
        (m["content"] for m in reversed(incoming_messages) if m.get("role") == "user"),
        None,
    )

    # Get shared conversation and fetch its full history from PostgreSQL
    conversation_id = await get_or_create_shared_conversation(db)
    pg_history = await fetch_history(db, conversation_id)

    # Store the new user message in PostgreSQL before calling OpenRouter
    if last_user_msg:
        await store_message(db, conversation_id, "user", last_user_msg)
        await db.commit()

    # Build the messages to send to OpenRouter:
    # [system prompt] + [full PG history including voice turns] + [new user message]
    final_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    final_messages.extend(pg_history)
    if last_user_msg:
        final_messages.append({"role": "user", "content": last_user_msg})

    headers = _openrouter_headers()
    payload = {
        "model": body.get("model", MODEL),
        "messages": final_messages,
        "stream": stream,
    }
    for key in ("temperature", "max_tokens", "top_p",
                "frequency_penalty", "presence_penalty", "stop"):
        if key in body:
            payload[key] = body[key]

    if stream:
        return StreamingResponse(
            _stream_response(headers, payload, conversation_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
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

        # Store the assistant reply in PostgreSQL
        assistant_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if assistant_reply:
            await store_message(db, conversation_id, "assistant", assistant_reply)
            await db.commit()

        return JSONResponse(content=data)

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenRouter timed out.")
    except httpx.RequestError as exc:
        logger.error("OpenRouter request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach OpenRouter.")


# ── Streaming helper ──────────────────────────────────────────────────────


async def _stream_response(headers: dict, payload: dict, conversation_id: str):
    """
    Open a streaming connection to OpenRouter, forward each SSE chunk to the
    caller, and store the complete assistant reply in PostgreSQL when done.

    Uses a fresh DB session (not the request-scoped Depends session) because
    the generator runs after the endpoint function has already returned.
    """
    model = payload.get("model", "unknown")
    collected_text: list[str] = []

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
                    if not line.strip():
                        continue
                    yield f"{line}\n\n"

                    # Collect delta text so we can store it in PostgreSQL
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                collected_text.append(delta)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

    except httpx.TimeoutException:
        logger.error("OpenRouter stream timed out")
        yield _error_as_sse("OpenRouter timed out. Please try again.", model=model)
        return
    except httpx.RequestError as exc:
        logger.error("OpenRouter stream connection error: %s", exc)
        yield _error_as_sse(
            "Could not connect to OpenRouter. Please try again.", model=model
        )
        return

    # Store the complete assistant reply in PostgreSQL after streaming finishes
    if collected_text and conversation_id:
        assistant_reply = "".join(collected_text)
        try:
            async with AsyncSessionLocal() as db:
                await store_message(db, conversation_id, "assistant", assistant_reply)
                await db.commit()
            logger.debug("Stored streamed assistant reply (%d chars)", len(assistant_reply))
        except Exception as exc:
            logger.error("Failed to store streamed assistant reply: %s", exc)

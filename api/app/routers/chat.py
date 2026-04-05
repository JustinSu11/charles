import asyncio
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException

_log = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx

from app.database import get_db
from app.models import ChatRequest, ChatResponse
from app.services.openrouter import get_openrouter_response
from app.services.conversation import get_or_create_shared_conversation
from app.services.ws_manager import manager
from app.services.skill_router import route as route_skills
from app.skills import run_skill

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    # 1. Resolve conversation
    if request.conversation_id is None:
        conversation_id = await get_or_create_shared_conversation(db)
    else:
        result = await db.execute(
            text("SELECT id FROM conversations WHERE id = :id"),
            {"id": str(request.conversation_id)},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="conversation_id not found")
        conversation_id = row[0]

    # 2. Fetch history for context
    history_result = await db.execute(
        text("""
            SELECT role, content FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": str(conversation_id)},
    )
    history = [{"role": r[0], "content": r[1]} for r in history_result.fetchall()]
    history.append({"role": "user", "content": request.message})

    # 3. Store user message (UUID generated in Python)
    user_message_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES (:id, :cid, 'user', :content)
        """),
        {"id": user_message_id, "cid": str(conversation_id), "content": request.message},
    )
    await db.commit()

    # 4. Resolve the active model (set via PUT /settings/model; falls back to env default)
    model_row = (await db.execute(
        text("SELECT value FROM app_state WHERE key = 'active_model'")
    )).fetchone()
    active_model = model_row[0] if model_row else None

    # 5. Route message to skills and fetch live data for any that activate.
    #    Each skill gets SKILL_TIMEOUT_SECS to fetch external data. If it
    #    exceeds the budget or errors, Charles replies without that context
    #    rather than blocking the whole request.
    SKILL_TIMEOUT_SECS = 8.0
    activated = route_skills(request.message)
    skill_context: str | None = None
    if activated:
        skill_blocks = []
        for name in activated:
            try:
                skill_blocks.append(
                    await asyncio.wait_for(run_skill(name), timeout=SKILL_TIMEOUT_SECS)
                )
            except asyncio.TimeoutError:
                _log.warning("Skill '%s' timed out after %.0fs — proceeding without it", name, SKILL_TIMEOUT_SECS)
            except Exception as exc:
                _log.warning("Skill '%s' failed — proceeding without it: %s", name, exc)
        if skill_blocks:
            skill_context = "\n\n---\n\n".join(skill_blocks)

    # 6. Call OpenRouter
    try:
        assistant_reply = await get_openrouter_response(
            history, model=active_model, skill_context=skill_context
        )
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            try:
                upstream = e.response.json()
                msg = upstream.get("error", {}).get("metadata", {}).get("raw", "Rate limit reached.")
            except Exception:
                msg = "Rate limit reached."
            raise HTTPException(status_code=429, detail=f"OpenRouter rate limit: {msg}")
        if status == 401:
            raise HTTPException(status_code=500, detail="OpenRouter API key is invalid.")
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {status}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenRouter timed out. Try again.")

    # 7. Store assistant reply
    assistant_message_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES (:id, :cid, 'assistant', :content)
        """),
        {"id": assistant_message_id, "cid": str(conversation_id), "content": assistant_reply},
    )
    await db.commit()

    # 8. Broadcast to all connected WebSocket clients
    await manager.broadcast({
        "type": "turn",
        "interface": request.interface,
        "conversation_id": str(conversation_id),
        "user": {
            "role": "user",
            "content": request.message,
            "message_id": user_message_id,
        },
        "assistant": {
            "role": "assistant",
            "content": assistant_reply,
            "message_id": assistant_message_id,
        },
    })

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=assistant_message_id,
        response=assistant_reply,
    )

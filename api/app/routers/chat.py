from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx
import uuid

from app.database import get_db
from app.models import ChatRequest, ChatResponse
from app.services.openrouter import get_openrouter_response

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Send a message to Charles.
    - Creates a new conversation if conversation_id is not provided.
    - Fetches full history, calls OpenRouter, stores both messages, returns reply.
    """

    # 1. Resolve or create conversation
    if request.conversation_id is None:
        result = await db.execute(
            text("INSERT INTO conversations (interface) VALUES (:interface) RETURNING id"), {"interface": request.interface},
        )
        await db.commit()
        conversation_id = result.scalar_one()
    else:
        result = await db.execute(
            text("SELECT id FROM conversations WHERE id = :id"), {"id": str(request.conversation_id)},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="conversation_id not found")
        conversation_id = row[0]

    # 2. Fetch existing history for context
    history_result = await db.execute(
        text("""
            SELECT role, content FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": str(conversation_id)}
    )
    history = [{"role": row[0], "content": row[1]} for row in history_result.fetchall()]

    # 3. Append the new user message to history
    history.append({"role": "user", "content": request.message})

    # 4 Store user message in DB
    user_msg_result = await db.execute(
        text("""
            INSERT INTO messages (conversation_id, role, content)
            VALUES (:cid, 'user', :content)
            RETURNING id
        """),
        {"cid": str(conversation_id), "content": request.message}
    )
    await db.commit()
    user_message_id = user_msg_result.scalar_one()

    # 5. Call OpenRouter
    try:
        assistant_reply = await get_openrouter_response(history)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            raise HTTPException(status_code=429, detail="OpenRouter rate limit reached. Try again shortly.")
        if status == 401:
            raise HTTPException(status_code=500, detail="OpenRouter API key is invalid.")
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {status}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenRouter timed out. Try again.")

    # 6. Store assistant's reply in DB
    assistant_msg_result = await db.execute(
        text("""
            INSERT INTO messages (conversation_id, role, content)
            VALUES (:cid, 'assistant', :content)
            RETURNING id
        """),
        {"cid": str(conversation_id), "content": assistant_reply}
    )
    await db.commit()
    assistant_message_id = assistant_msg_result.scalar_one()

    return ChatResponse(
        conversation_id = conversation_id,
        message_id = assistant_message_id,
        response = assistant_reply,
    )
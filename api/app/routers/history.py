from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models import HistoryResponse, MessageOut

router = APIRouter()


@router.get("/history/shared", response_model=HistoryResponse)
async def get_shared_history(db: AsyncSession = Depends(get_db)):
    """Return full history for the shared conversation. 404 if none exists yet."""
    result = await db.execute(
        text("SELECT value FROM app_state WHERE key = 'shared_conversation_id'")
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No shared conversation yet")

    conversation_id = row[0]
    msg_result = await db.execute(
        text("""
            SELECT id, role, content, created_at FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": conversation_id},
    )
    messages = [
        MessageOut(
            id=r[0],
            role=r[1],
            content=r[2],
            created_at=datetime.fromisoformat(str(r[3]).replace(" ", "T")),
        )
        for r in msg_result.fetchall()
    ]
    return HistoryResponse(conversation_id=conversation_id, interface="voice", messages=messages)


@router.get("/history/{conversation_id}", response_model=HistoryResponse)
async def get_history(conversation_id: str, db: AsyncSession = Depends(get_db)):
    conv_result = await db.execute(
        text("SELECT id, interface FROM conversations WHERE id = :id"),
        {"id": conversation_id},
    )
    conv = conv_result.fetchone()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        text("""
            SELECT id, role, content, created_at FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": conversation_id},
    )
    messages = [
        MessageOut(
            id=row[0],
            role=row[1],
            content=row[2],
            created_at=datetime.fromisoformat(str(row[3]).replace(" ", "T")),
        )
        for row in msg_result.fetchall()
    ]
    return HistoryResponse(conversation_id=conv[0], interface=conv[1], messages=messages)


@router.delete("/history/{conversation_id}", status_code=204)
async def delete_history(conversation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id FROM conversations WHERE id = :id"),
        {"id": conversation_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Delete messages first (FK child), then the conversation row (FK parent).
    # Also clear the shared_conversation_id pointer so get_or_create_shared_conversation()
    # generates a fresh UUID on the next request rather than returning a deleted ID.
    await db.execute(
        text("DELETE FROM messages WHERE conversation_id = :id"),
        {"id": conversation_id},
    )
    await db.execute(
        text("DELETE FROM conversations WHERE id = :id"),
        {"id": conversation_id},
    )
    await db.execute(
        text("DELETE FROM app_state WHERE key = 'shared_conversation_id' AND value = :id"),
        {"id": conversation_id},
    )
    await db.commit()
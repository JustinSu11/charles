from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models import HistoryResponse, MessageOut

router = APIRouter()

@router.get("/history/{conversation_id}", response_model = HistoryResponse)
async def get_history(conversation_id: str, db: AsyncSession = Depends(get_db)):
    # return full message history for a conversation

    conv_result = await db.execute(
        text("SELECT id, interface FROM conversations WHERE id = :id"),
        {"id": conversation_id}
    )
    conv = conv_result.fetchone()
    if not conv:
            raise HTTPException(status_code = 404, detail = "Conversation not found")
    
    msg_result = await db.execute(
          text("""
                SELECT id, role, content, created_at FROM messages
                WHERE conversation_id = :cid
                ORDER BY created_at ASC
            """),
        {"cid": conversation_id}
    )
    messages = [
          MessageOut(
                id = row[0], 
                role = row[1], 
                content = row[2], 
                created_at = row[3]
            ) for row in msg_result.fetchall()
    ]
    return HistoryResponse(
        conversation_id = conv[0],
        interface = conv[1],
        messages = messages
    )

@router.delete("/history/{conversation_id}", status_code = 204)
async def delete_history(conversation_id: str, db: AsyncSession = Depends(get_db)):
    # delete a conversation and all its messages
    result = await db.execute(
         text("SELECT id FROM conversations WHERE id = :id"),
         {"id": conversation_id}
    )
    if not result.fetchone():
         raise HTTPException(status_code = 404, detail = "Conversation not found")
    
    await db.execute(
        text("DELETE FROM conversations WHERE id = :id"),
        {"id": conversation_id}
    )
    await db.commit()
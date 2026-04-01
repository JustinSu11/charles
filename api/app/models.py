from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Literal

"""
incoming request body for POST /chat
If conversation_id is none then a new conversation will be started
"""
class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    interface: Literal["voice", "web"] = "web"
    message: str


"""
response body for POST /chat
"""
class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    response: str


# A single message returned in history
class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

#Response body for Get /history/{conversation_id}
class HistoryResponse(BaseModel):
    conversation_id: UUID
    interface: Literal["voice", "web"]
    messages: list[MessageOut]
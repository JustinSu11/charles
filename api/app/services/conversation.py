"""
conversation.py — Shared conversation helpers.
"""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_or_create_shared_conversation(db: AsyncSession) -> str:
    result = await db.execute(
        text("SELECT value FROM app_state WHERE key = 'shared_conversation_id'")
    )
    row = result.fetchone()
    if row:
        return row[0]

    conversation_id = str(uuid.uuid4())

    # Both inserts in one commit — if the process crashes between them,
    # a partial state is never written (no orphaned conversation row).
    await db.execute(
        text("INSERT INTO conversations (id, interface) VALUES (:id, 'voice')"),
        {"id": conversation_id},
    )
    await db.execute(
        text("INSERT INTO app_state (key, value) VALUES ('shared_conversation_id', :val)"),
        {"val": conversation_id},
    )
    await db.commit()
    return conversation_id


async def fetch_history(db: AsyncSession, conversation_id: str) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT role, content FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": conversation_id},
    )
    return [{"role": row[0], "content": row[1]} for row in result.fetchall()]


async def store_message(
    db: AsyncSession, conversation_id: str, role: str, content: str
) -> str:
    """Insert a message and return its UUID string."""
    msg_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES (:id, :cid, :role, :content)
        """),
        {"id": msg_id, "cid": conversation_id, "role": role, "content": content},
    )
    return msg_id

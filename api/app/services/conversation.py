"""
conversation.py — Shared conversation helpers.

Both the voice (/chat) and web (/v1/chat/completions) interfaces write to
a single "shared" conversation so context is always combined.  The shared
conversation ID is persisted in the app_state table.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_or_create_shared_conversation(db: AsyncSession) -> str:
    """
    Return the shared conversation ID.

    On first call, creates a new conversation (interface='voice' since voice
    normally starts it) and stores the ID in app_state for all future calls.
    """
    result = await db.execute(
        text("SELECT value FROM app_state WHERE key = 'shared_conversation_id'")
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Create the shared conversation
    result = await db.execute(
        text("INSERT INTO conversations (interface) VALUES ('voice') RETURNING id")
    )
    await db.commit()
    conversation_id = str(result.scalar_one())

    # Persist so every future call uses the same conversation
    await db.execute(
        text("INSERT INTO app_state (key, value) VALUES ('shared_conversation_id', :val)"),
        {"val": conversation_id},
    )
    await db.commit()
    return conversation_id


async def fetch_history(db: AsyncSession, conversation_id: str) -> list[dict]:
    """Return all messages for *conversation_id* ordered chronologically."""
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
    result = await db.execute(
        text("""
            INSERT INTO messages (conversation_id, role, content)
            VALUES (:cid, :role, :content)
            RETURNING id
        """),
        {"cid": conversation_id, "role": role, "content": content},
    )
    return str(result.scalar_one())

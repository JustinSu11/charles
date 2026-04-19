"""
test_history.py — Integration tests for the three history endpoints.

GET  /history/shared      — the unified voice+web conversation
GET  /history/{id}        — a specific conversation by UUID
DELETE /history/{id}      — removes conversation + clears the shared pointer

All I/O flows through the injected in-memory test DB from conftest.py.
The patched_openrouter fixture prevents real OpenRouter calls when seeding data.
"""

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

async def _do_chat(client, message="hello", interface="web"):
    resp = await client.post("/chat", json={"message": message, "interface": interface})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── GET /history/shared ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shared_history_empty(client):
    resp = await client.get("/history/shared")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_shared_history_after_one_turn(client, patched_openrouter):
    await _do_chat(client, "hello")

    resp = await client.get("/history/shared")
    assert resp.status_code == 200

    data = resp.json()
    messages = data["messages"]
    assert len(messages) == 2
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "hello"),
        ("assistant", "mocked reply"),
    ]


@pytest.mark.asyncio
async def test_shared_history_message_fields(client, patched_openrouter):
    await _do_chat(client)

    resp = await client.get("/history/shared")
    messages = resp.json()["messages"]

    for msg in messages:
        assert "id" in msg
        assert "role" in msg
        assert "content" in msg
        assert "created_at" in msg


@pytest.mark.asyncio
async def test_shared_history_three_turns_in_order(client, patched_openrouter):
    for i in range(3):
        patched_openrouter.return_value = f"reply {i}"
        await _do_chat(client, f"message {i}")

    resp = await client.get("/history/shared")
    messages = resp.json()["messages"]
    assert len(messages) == 6  # 3 user + 3 assistant

    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"] * 3


# ── GET /history/{conversation_id} ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_history_by_id(client, patched_openrouter):
    chat_resp = await _do_chat(client)
    conv_id = chat_resp["conversation_id"]

    resp = await client.get(f"/history/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert len(data["messages"]) == 2


@pytest.mark.asyncio
async def test_get_history_nonexistent_id(client):
    resp = await client.get("/history/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ── DELETE /history/{conversation_id} ────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_history_returns_204(client, patched_openrouter):
    chat_resp = await _do_chat(client)
    conv_id = chat_resp["conversation_id"]

    resp = await client.delete(f"/history/{conv_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_history_then_get_returns_404(client, patched_openrouter):
    chat_resp = await _do_chat(client)
    conv_id = chat_resp["conversation_id"]

    await client.delete(f"/history/{conv_id}")

    resp = await client.get(f"/history/{conv_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_history_clears_shared_pointer(client, patched_openrouter):
    chat_resp = await _do_chat(client)
    conv_id = chat_resp["conversation_id"]

    await client.delete(f"/history/{conv_id}")

    resp = await client.get("/history/shared")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_then_chat_creates_new_conversation(client, patched_openrouter):
    """After deleting the shared conversation, a new /chat creates a fresh one."""
    first = await _do_chat(client)
    old_conv_id = first["conversation_id"]

    await client.delete(f"/history/{old_conv_id}")

    second = await _do_chat(client, "new message")
    new_conv_id = second["conversation_id"]

    assert new_conv_id != old_conv_id

    resp = await client.get("/history/shared")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client):
    resp = await client.delete("/history/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_history_shared_empty(client):
    resp = await client.get("/history/shared")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_creates_shared_history(client):
    with patch(
        "app.routers.chat.get_openrouter_response",
        new=AsyncMock(return_value="Hello from Charles!"),
    ):
        resp = await client.post(
            "/chat", json={"message": "Hello", "interface": "web"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "Hello from Charles!"
    assert "conversation_id" in data

    hist = await client.get("/history/shared")
    assert hist.status_code == 200
    messages = hist.json()["messages"]
    # Assert full (role, content) sequence — robust against same-second timestamp ties
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Hello"),
        ("assistant", "Hello from Charles!"),
    ]

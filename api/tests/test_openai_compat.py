"""
test_openai_compat.py — Tests for the OpenAI-compatible /v1/ endpoints.

Open WebUI uses these endpoints exclusively, so regressions here break the
entire web interface. Non-streaming and error paths are covered.
"""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── _error_as_sse() pure function ─────────────────────────────────────────────

def test_error_as_sse_format():
    from app.routers.openai_compat import _error_as_sse
    result = _error_as_sse("Something went wrong")
    assert result.startswith("data: ")
    assert result.endswith("data: [DONE]\n\n")
    # The embedded JSON must be parseable
    first_line = result.split("\n\n")[0]
    assert first_line.startswith("data: ")
    chunk = json.loads(first_line[len("data: "):])
    assert "⚠️" in chunk["choices"][0]["delta"]["content"]


# ── GET /v1/models ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_models_no_api_key_returns_500(client):
    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", ""):
        resp = await client.get("/v1/models")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_models_returns_proxied_list(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"id": "openai/gpt-4o", "context_length": 128000}]
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch("app.routers.openai_compat.httpx.AsyncClient", return_value=mock_client):
            resp = await client.get("/v1/models")

    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert any(m["id"] == "openai/gpt-4o" for m in data["data"])


@pytest.mark.asyncio
async def test_list_models_request_error_falls_back_to_single_model(client):
    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch(
            "app.routers.openai_compat.httpx.AsyncClient",
            side_effect=httpx.RequestError("network error"),
        ):
            resp = await client.get("/v1/models")

    assert resp.status_code == 200
    # Should return at least the default MODEL in the fallback list
    data = resp.json()
    assert len(data["data"]) >= 1


# ── POST /v1/chat/completions (non-streaming) ─────────────────────────────────

def _make_openrouter_response(content="Hello from Charles"):
    """Build a mock non-streaming OpenRouter response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "id": "test-id",
        "model": "openai/gpt-4o",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return mock_resp


@pytest.mark.asyncio
async def test_chat_completions_non_streaming_happy_path(client, patched_openrouter):
    mock_resp = _make_openrouter_response("Hi there!")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    payload = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }

    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch("app.routers.openai_compat.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post("/v1/chat/completions", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_chat_completions_reply_stored_in_db(client, patched_openrouter):
    """Non-streaming reply must be persisted so GET /history/shared returns it."""
    mock_resp = _make_openrouter_response("stored reply")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    payload = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "remember this"}],
        "stream": False,
    }

    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch("app.routers.openai_compat.httpx.AsyncClient", return_value=mock_client):
            await client.post("/v1/chat/completions", json=payload)

    hist = await client.get("/history/shared")
    assert hist.status_code == 200
    messages = hist.json()["messages"]
    contents = [m["content"] for m in messages]
    assert "stored reply" in contents


@pytest.mark.asyncio
async def test_chat_completions_timeout_returns_504(client):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    payload = {"model": "x", "messages": [{"role": "user", "content": "hi"}], "stream": False}

    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch("app.routers.openai_compat.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post("/v1/chat/completions", json=payload)

    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_chat_completions_request_error_returns_502(client):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("network"))

    payload = {"model": "x", "messages": [{"role": "user", "content": "hi"}], "stream": False}

    with patch("app.routers.openai_compat.OPENROUTER_API_KEY", "test-key"):
        with patch("app.routers.openai_compat.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post("/v1/chat/completions", json=payload)

    assert resp.status_code == 502

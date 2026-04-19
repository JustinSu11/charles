"""
test_chat_errors.py — Tests for the five error branches in POST /chat,
plus model-selection propagation and skill resilience.

These error paths were previously completely untested despite being the most
likely cause of confusing user-facing failures.
"""

import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

async def _chat(client, message="hello", interface="web", conversation_id=None):
    payload = {"message": message, "interface": interface}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return await client.post("/chat", json=payload)


def _http_error(status_code: int, body: dict | None = None):
    """Build an httpx.HTTPStatusError with a given status code."""
    request = httpx.Request("POST", "https://openrouter.ai/")
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body or {}
    return httpx.HTTPStatusError("error", request=request, response=response)


# ── happy path regression ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_happy_path(client, patched_openrouter):
    resp = await _chat(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "mocked reply"
    assert "conversation_id" in data
    assert "message_id" in data


# ── explicit conversation_id ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_explicit_valid_conversation_id(client, patched_openrouter):
    first = await _chat(client)
    conv_id = first.json()["conversation_id"]

    second = await _chat(client, message="follow up", conversation_id=conv_id)
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id


@pytest.mark.asyncio
async def test_chat_nonexistent_conversation_id_returns_404(client, patched_openrouter):
    resp = await _chat(client, conversation_id="00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ── OpenRouter HTTP error branches ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_openrouter_429_returns_429(client):
    err = _http_error(429, {"error": {"metadata": {"raw": "Rate limit reached."}}})
    with patch("app.routers.chat.get_openrouter_response", new=AsyncMock(side_effect=err)):
        resp = await _chat(client)
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_openrouter_401_returns_500(client):
    err = _http_error(401)
    with patch("app.routers.chat.get_openrouter_response", new=AsyncMock(side_effect=err)):
        resp = await _chat(client)
    assert resp.status_code == 500
    assert "invalid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_openrouter_503_returns_502(client):
    err = _http_error(503)
    with patch("app.routers.chat.get_openrouter_response", new=AsyncMock(side_effect=err)):
        resp = await _chat(client)
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_chat_openrouter_timeout_returns_504(client):
    with patch(
        "app.routers.chat.get_openrouter_response",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        resp = await _chat(client)
    assert resp.status_code == 504


# ── skill resilience ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_succeeds_when_skill_raises(client, patched_openrouter):
    """A skill exception must not bubble up — chat still returns 200."""
    with patch("app.routers.chat.run_skill", new=AsyncMock(side_effect=RuntimeError("skill boom"))):
        with patch("app.routers.chat.route_skills", return_value=["tech_news"]):
            resp = await _chat(client, message="hacker news")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_succeeds_when_skill_times_out(client, patched_openrouter):
    """A skill asyncio.TimeoutError must not kill the request."""
    async def _slow(*_):
        await asyncio.sleep(100)

    with patch("app.routers.chat.run_skill", new=_slow):
        with patch("app.routers.chat.route_skills", return_value=["tech_news"]):
            with patch("app.routers.chat.asyncio.wait_for", side_effect=asyncio.TimeoutError):
                resp = await _chat(client, message="hacker news")
    assert resp.status_code == 200


# ── model selection propagation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_model_forwarded_to_openrouter(client):
    """When app_state has an active_model row, it must be passed to the LLM call."""
    mock = AsyncMock(return_value="ok")
    with patch("app.routers.chat.get_openrouter_response", new=mock):
        # Seed the active_model via the settings endpoint
        await client.put("/settings/model", json={"model": "openai/gpt-4o"})
        resp = await _chat(client)

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs.get("model") == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_no_active_model_passes_none(client):
    """Without an active_model row, model=None must be forwarded (env default used upstream)."""
    mock = AsyncMock(return_value="ok")
    with patch("app.routers.chat.get_openrouter_response", new=mock):
        resp = await _chat(client)

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs.get("model") is None


# ── interface propagation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_interface_forwarded(client):
    mock = AsyncMock(return_value="ok")
    with patch("app.routers.chat.get_openrouter_response", new=mock):
        resp = await _chat(client, interface="voice")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs.get("interface") == "voice"

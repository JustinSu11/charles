"""
test_settings.py — Tests for model selection persistence and the model catalogue cache.

The cache is module-level state in settings.py, so each cache-related test must
reset it before running to prevent ordering-dependent failures.
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.routers.settings as settings_module


def _reset_cache():
    """Clear the in-process model list cache between tests."""
    settings_module._cached_models = []
    settings_module._cached_at = 0.0


# ── GET /settings/model ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_model_returns_default_when_no_row(client):
    resp = await client.get("/settings/model")
    assert resp.status_code == 200
    # Must return the env-default model (whatever OPENROUTER_MODEL resolves to)
    assert "model" in resp.json()
    assert resp.json()["model"]  # non-empty


# ── PUT + GET round-trip ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_model_returns_selected_model(client):
    resp = await client.put("/settings/model", json={"model": "openai/gpt-4o"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_set_then_get_round_trip(client):
    await client.put("/settings/model", json={"model": "openai/gpt-4o"})
    resp = await client.get("/settings/model")
    assert resp.json()["model"] == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_second_put_overrides_first(client):
    """Upsert semantics: second PUT wins, no duplicate rows."""
    await client.put("/settings/model", json={"model": "openai/gpt-4o"})
    await client.put("/settings/model", json={"model": "anthropic/claude-3-haiku"})
    resp = await client.get("/settings/model")
    assert resp.json()["model"] == "anthropic/claude-3-haiku"


# ── GET /models cache behaviour ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_models_no_api_key_returns_empty(client):
    _reset_cache()
    with patch.object(settings_module, "_OPENROUTER_KEY", ""):
        resp = await client.get("/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == []


@pytest.mark.asyncio
async def test_get_models_cache_hit_calls_httpx_once(client):
    _reset_cache()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o", "name": "GPT-4o", "context_length": 128000},
            {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5", "context_length": 16000},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(settings_module, "_OPENROUTER_KEY", "test-key"):
        with patch("app.routers.settings.httpx.AsyncClient", return_value=mock_client):
            await client.get("/models")  # first call — hits httpx
            await client.get("/models")  # second call — cache hit

    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_models_cache_expires_after_ttl(client):
    _reset_cache()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": [{"id": "x/y", "name": "Y", "context_length": 1000}]}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(settings_module, "_OPENROUTER_KEY", "test-key"):
        with patch("app.routers.settings.httpx.AsyncClient", return_value=mock_client):
            await client.get("/models")  # populates cache

            # Artificially expire the cache
            settings_module._cached_at = time.monotonic() - (settings_module._MODELS_CACHE_TTL + 1)

            await client.get("/models")  # should re-fetch

    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_get_models_returns_stale_cache_on_error(client):
    _reset_cache()
    settings_module._cached_models = [{"id": "stale/model", "name": "Stale"}]
    settings_module._cached_at = 0.0  # force expiry on next check

    with patch.object(settings_module, "_OPENROUTER_KEY", "test-key"):
        with patch("app.routers.settings.httpx.AsyncClient", side_effect=Exception("network down")):
            resp = await client.get("/models")

    # Should fall back to the stale cache without raising
    assert resp.status_code == 200
    assert resp.json()["models"] == [{"id": "stale/model", "name": "Stale"}]

    _reset_cache()

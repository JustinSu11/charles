"""
test_ws_manager.py — Unit tests for the WebSocket ConnectionManager.

Uses AsyncMock to simulate WebSocket objects — no real network connections needed.
The key invariant: dead sockets must be pruned so broadcast never crashes,
and live sockets must always receive the payload.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.ws_manager import ConnectionManager


def _make_ws(raises_on_send=False):
    """Create a mock WebSocket. Set raises_on_send=True to simulate a dead connection."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    if raises_on_send:
        ws.send_text = AsyncMock(side_effect=Exception("connection closed"))
    else:
        ws.send_text = AsyncMock()
    return ws


# ── connect / disconnect ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_calls_accept(self=None):
    mgr = ConnectionManager()
    ws = _make_ws()
    await mgr.connect(ws)
    ws.accept.assert_called_once()


@pytest.mark.asyncio
async def test_connect_adds_to_list():
    mgr = ConnectionManager()
    ws = _make_ws()
    await mgr.connect(ws)
    assert ws in mgr._connections


@pytest.mark.asyncio
async def test_disconnect_removes_from_list():
    mgr = ConnectionManager()
    ws = _make_ws()
    await mgr.connect(ws)
    mgr.disconnect(ws)
    assert ws not in mgr._connections


# ── broadcast ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_reaches_all_live_clients():
    mgr = ConnectionManager()
    ws1, ws2 = _make_ws(), _make_ws()
    await mgr.connect(ws1)
    await mgr.connect(ws2)

    payload = {"type": "turn", "content": "hello"}
    await mgr.broadcast(payload)

    expected = json.dumps(payload, default=str)
    ws1.send_text.assert_called_once_with(expected)
    ws2.send_text.assert_called_once_with(expected)


@pytest.mark.asyncio
async def test_broadcast_prunes_dead_socket():
    mgr = ConnectionManager()
    dead = _make_ws(raises_on_send=True)
    live = _make_ws()
    await mgr.connect(dead)
    await mgr.connect(live)

    await mgr.broadcast({"type": "test"})

    # Dead socket pruned, live socket still present
    assert dead not in mgr._connections
    assert live in mgr._connections


@pytest.mark.asyncio
async def test_broadcast_live_client_still_receives_when_dead_present():
    mgr = ConnectionManager()
    dead = _make_ws(raises_on_send=True)
    live = _make_ws()
    await mgr.connect(dead)
    await mgr.connect(live)

    payload = {"type": "test", "value": 42}
    await mgr.broadcast(payload)

    live.send_text.assert_called_once_with(json.dumps(payload, default=str))


@pytest.mark.asyncio
async def test_broadcast_empty_connections_no_error():
    mgr = ConnectionManager()
    # Should not raise even with no connections
    await mgr.broadcast({"type": "test"})

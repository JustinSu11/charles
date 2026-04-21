"""
test_voice_api_client.py — Unit tests for api_client.send_message() and helpers.

The error strings returned by send_message() are spoken back to the user by TTS.
If an HTTP status code is handled incorrectly, the user either hears a confusing
message or silence — so the exact error strings are part of the public contract.

All requests.post / requests.get calls are mocked.
Module-level state (_conversation_id) is reset between tests via a fixture.
"""

import pytest
from unittest.mock import MagicMock, patch, call

import api_client


@pytest.fixture(autouse=True)
def reset_conversation_state():
    """Reset module-level conversation ID before each test."""
    api_client._conversation_id = None
    yield
    api_client._conversation_id = None


def _mock_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = (200 <= status_code < 300)
    resp.json.return_value = json_data or {}
    resp.text = str(json_data)
    return resp


# ── Happy path ────────────────────────────────────────────────────────────────

def test_send_message_returns_reply():
    resp = _mock_response(200, {"response": "Hello!", "conversation_id": "abc-123"})
    with patch("api_client.requests.post", return_value=resp) as mock_post:
        result = api_client.send_message("hi")
    assert result == "Hello!"


def test_send_message_stores_conversation_id():
    resp = _mock_response(200, {"response": "Hi", "conversation_id": "conv-999"})
    with patch("api_client.requests.post", return_value=resp):
        api_client.send_message("hello")
    assert api_client._conversation_id == "conv-999"


def test_second_send_includes_conversation_id_in_payload():
    resp = _mock_response(200, {"response": "Ok", "conversation_id": "conv-1"})
    with patch("api_client.requests.post", return_value=resp) as mock_post:
        api_client.send_message("first")
        api_client.send_message("second")

    second_call_kwargs = mock_post.call_args_list[1]
    payload = second_call_kwargs[1]["json"]  # keyword arg
    assert payload.get("conversation_id") == "conv-1"


# ── Connection / timeout errors ───────────────────────────────────────────────

def test_connection_error_returns_human_readable_string():
    with patch("api_client.requests.post", side_effect=api_client.requests.exceptions.ConnectionError):
        result = api_client.send_message("hello")
    assert isinstance(result, str)
    assert len(result) > 0
    # Must not raise — caller speaks the error via TTS


def test_timeout_error_returns_human_readable_string():
    with patch("api_client.requests.post", side_effect=api_client.requests.exceptions.Timeout):
        result = api_client.send_message("hello")
    assert isinstance(result, str)
    assert len(result) > 0


# ── HTTP error status codes ───────────────────────────────────────────────────

def test_429_returns_rate_limit_string():
    resp = _mock_response(429)
    with patch("api_client.requests.post", return_value=resp):
        result = api_client.send_message("hello")
    assert "rate limit" in result.lower() or "wait" in result.lower()


def test_504_returns_upstream_timeout_string():
    resp = _mock_response(504)
    with patch("api_client.requests.post", return_value=resp):
        result = api_client.send_message("hello")
    assert isinstance(result, str)
    assert len(result) > 0


def test_generic_500_returns_error_string_with_status_code():
    resp = _mock_response(500)
    with patch("api_client.requests.post", return_value=resp):
        result = api_client.send_message("hello")
    assert "500" in result


# ── 404 retry with conversation reset ────────────────────────────────────────

def test_404_resets_conversation_id_and_retries():
    """
    A 404 on an existing conversation_id means the conversation was deleted.
    The client must reset the ID and retry once with conversation_id=None.
    """
    api_client._conversation_id = "stale-conv-id"

    not_found = _mock_response(404)
    ok = _mock_response(200, {"response": "fresh start", "conversation_id": "new-conv"})

    with patch("api_client.requests.post", side_effect=[not_found, ok]) as mock_post:
        result = api_client.send_message("hello")

    assert result == "fresh start"
    assert mock_post.call_count == 2

    # Second call must NOT include the stale conversation_id
    second_payload = mock_post.call_args_list[1][1]["json"]
    assert "conversation_id" not in second_payload or second_payload.get("conversation_id") is None


# ── reset_conversation / get_conversation_id ─────────────────────────────────

def test_reset_conversation_clears_id():
    api_client._conversation_id = "some-id"
    api_client.reset_conversation()
    assert api_client.get_conversation_id() is None


def test_get_conversation_id_none_before_first_send():
    assert api_client.get_conversation_id() is None


# ── health_check() ───────────────────────────────────────────────────────────

def test_health_check_returns_true_when_ok():
    resp = _mock_response(200, {"status": "ok"})
    with patch("api_client.requests.get", return_value=resp):
        assert api_client.health_check() is True


def test_health_check_returns_false_on_exception():
    with patch("api_client.requests.get", side_effect=Exception("no connection")):
        assert api_client.health_check() is False


def test_health_check_returns_false_when_status_not_ok():
    resp = _mock_response(200, {"status": "degraded"})
    with patch("api_client.requests.get", return_value=resp):
        assert api_client.health_check() is False

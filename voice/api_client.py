"""
api_client.py — HTTP client that sends transcribed text to the Charles API.

Manages a single conversation session across the lifetime of the voice service
so that all turns in one session share history context.  A new conversation is
created automatically on first use (or when reset() is called).

Environment variables:
    CHARLES_API_URL   — Base URL for the Charles API  (default: http://localhost:8000)
    VOICE_TIMEOUT     — Request timeout in seconds      (default: 30)
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

API_BASE_URL: str = os.getenv("CHARLES_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT: float = float(os.getenv("VOICE_TIMEOUT", "30"))

# ── State ─────────────────────────────────────────────────────────────────────

# The current voice-session conversation ID.  None means "let the API create one
# on the next request and remember it for subsequent turns."
_conversation_id: Optional[str] = None


# ── Public API ────────────────────────────────────────────────────────────────

def send_message(text: str) -> str:
    """
    Send *text* to ``POST /chat`` and return Charles's reply.

    The conversation ID from the previous call is included so the API can
    build full context.  On the first call the API creates a new conversation
    and we persist its ID for all subsequent calls.

    Parameters
    ----------
    text
        The transcribed user utterance.

    Returns
    -------
    str
        The assistant reply text, or an error description suitable for TTS.

    Raises
    ------
    Does **not** raise — all HTTP and connection errors are caught and turned
    into human-readable error strings so the caller can speak them back.
    """
    global _conversation_id

    payload: dict = {
        "message": text,
        "interface": "voice",
    }
    if _conversation_id:
        payload["conversation_id"] = _conversation_id

    logger.info(
        "Sending to Charles API (conversation=%s): %r",
        _conversation_id or "new",
        text[:80],
    )

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat",
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        msg = "I can't reach the Charles API. Make sure the Docker containers are running."
        logger.error(msg)
        return msg
    except requests.exceptions.Timeout:
        msg = "The Charles API timed out. Please try again."
        logger.error(msg)
        return msg

    if response.status_code == 429:
        msg = "I've hit a rate limit with the AI provider. Please wait a moment and try again."
        logger.warning("Rate limit (429) from Charles API")
        return msg

    if response.status_code == 504:
        msg = "The AI provider timed out. Please try again in a few seconds."
        logger.warning("Upstream timeout (504) from Charles API")
        return msg

    if not response.ok:
        msg = f"Charles API returned an error: {response.status_code}."
        logger.error("Charles API error %d: %s", response.status_code, response.text[:200])
        return msg

    data: dict = response.json()
    reply: str = data.get("response", "")
    new_conv_id: Optional[str] = data.get("conversation_id")

    if new_conv_id and _conversation_id is None:
        _conversation_id = str(new_conv_id)
        logger.info("New conversation created: %s", _conversation_id)

    logger.info("Charles replied: %r", reply[:120])
    return reply


def reset_conversation() -> None:
    """
    Forget the current conversation ID so the next ``send_message()`` call
    starts a fresh conversation.

    Useful if the user says something like "Hey Charles, new conversation."
    """
    global _conversation_id
    logger.info("Resetting conversation (was: %s)", _conversation_id)
    _conversation_id = None


def get_conversation_id() -> Optional[str]:
    """Return the active conversation ID, or None if no session has started."""
    return _conversation_id


def health_check() -> bool:
    """
    Ping ``GET /health`` and return True if the API is reachable and healthy.

    Used at startup to warn the user if the Docker backend isn't running yet.
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        ok = resp.ok and resp.json().get("status") == "ok"
        logger.debug("Health check: %s", "ok" if ok else "unhealthy")
        return ok
    except Exception as exc:
        logger.debug("Health check failed: %s", exc)
        return False

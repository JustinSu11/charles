"""
tts.py — Microsoft Edge Neural TTS pipeline.

Uses edge-tts to stream high-quality Azure Neural voices (no API key needed).
Audio is returned as MP3, decoded in-process by miniaudio, then played via
the same play_wav_bytes() path as before.

Voice options (default: en-US-GuyNeural)
-----------------------------------------
  Male   : en-US-GuyNeural, en-US-DavisNeural, en-US-ChristopherNeural
  Female : en-US-JennyNeural, en-US-AriaNeural, en-US-SaraNeural

Override with EDGE_VOICE in your .env file.
Full voice list: https://bit.ly/edge-tts-voices

Environment variables:
    EDGE_VOICE   — voice name          (default: en-US-GuyNeural)
    EDGE_RATE    — speed adjustment    (default: +0%, try +10% for slightly faster)
    EDGE_VOLUME  — volume adjustment   (default: +0%)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import threading
import wave
from typing import Optional

import edge_tts
import miniaudio

from audio import play_wav_bytes

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

EDGE_VOICE: str  = os.getenv("EDGE_VOICE",  "en-US-GuyNeural")
EDGE_RATE: str   = os.getenv("EDGE_RATE",   "+0%")
EDGE_VOLUME: str = os.getenv("EDGE_VOLUME", "+0%")

# ── Text preprocessing ────────────────────────────────────────────────────────

def _clean_for_tts(text: str) -> str:
    """
    Strip Markdown formatting and normalise punctuation before synthesis.

    LLM responses are written in Markdown for the web UI — feeding them raw
    to TTS causes Charles to say things like "asterisk asterisk" or "hash hash".
    This function strips those artefacts so only natural spoken text remains.
    """
    # ── Code blocks: replace with a brief spoken label so the user knows
    #    something was omitted rather than hearing garbled symbols
    text = re.sub(r'```[\s\S]*?```', 'code block omitted', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)           # inline code → bare text

    # ── Markdown formatting characters
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **bold**
    text = re.sub(r'\*(.+?)\*',     r'\1', text)        # *italic*
    text = re.sub(r'__(.+?)__',     r'\1', text)        # __bold__
    text = re.sub(r'_(.+?)_',       r'\1', text)        # _italic_
    text = re.sub(r'~~(.+?)~~',     r'\1', text)        # ~~strikethrough~~
    text = re.sub(r'#{1,6}\s+',     '',    text)        # ## Headings
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [link](url) → link text

    # ── List items: strip bullet/number characters
    text = re.sub(r'^\s*[-*+]\s+', '',  text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '',  text, flags=re.MULTILINE)

    # ── Horizontal rules and repeated punctuation
    text = re.sub(r'-{2,}',  ' ',  text)               # --- → space
    text = re.sub(r'={2,}',  ' ',  text)               # === → space
    text = re.sub(r'\.{2,}', '.',  text)               # ... → single period
    text = re.sub(r'[*_~|>]+', '', text)               # stray Markdown characters

    # ── Whitespace normalisation
    text = re.sub(r'\n+', ' ', text)                   # newlines → spaces
    text = re.sub(r' {2,}', ' ', text)                 # collapse multiple spaces

    return text.strip()


# ── Interruption support ──────────────────────────────────────────────────────

_playback_lock = threading.Lock()
_stop_playback = threading.Event()


def stop_speaking() -> None:
    """
    Signal that the current TTS playback should abort.

    Call this from the wake word callback so that detecting "Hey Charles"
    mid-sentence immediately stops Charles and listens again.
    """
    _stop_playback.set()


# ── Audio generation ──────────────────────────────────────────────────────────

async def _generate_mp3(text: str) -> bytes:
    """Stream audio from edge-tts and return the full MP3 bytes."""
    communicate = edge_tts.Communicate(text, voice=EDGE_VOICE, rate=EDGE_RATE, volume=EDGE_VOLUME)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Decode MP3 bytes to WAV bytes using miniaudio (no ffmpeg required)."""
    decoded = miniaudio.decode(
        mp3_bytes,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=24_000,
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(24_000)
        wf.writeframes(bytes(decoded.samples))
    return buf.getvalue()


# ── Public API ────────────────────────────────────────────────────────────────

def speak(
    text: str,
    output_device_index: Optional[int] = None,
) -> None:
    """
    Convert *text* to speech and play it through the speakers.

    Blocks until playback is complete **or** ``stop_speaking()`` is called.

    Parameters
    ----------
    text
        The text to synthesise.  Markdown is stripped automatically by
        ``_clean_for_tts`` before the text is sent to the TTS engine.
    output_device_index
        Speaker device index.  None → system default.
    """
    if not text or not text.strip():
        return

    _stop_playback.clear()
    clean = _clean_for_tts(text)

    if not clean:
        return

    logger.info("Speaking: %r", clean[:80])

    with _playback_lock:
        try:
            mp3_bytes = asyncio.run(_generate_mp3(clean))

            if _stop_playback.is_set():
                logger.debug("TTS playback aborted before it started")
                return

            wav_bytes = _mp3_to_wav(mp3_bytes)
            play_wav_bytes(wav_bytes, output_device_index=output_device_index)

        except Exception as exc:
            logger.error("TTS error: %s", exc, exc_info=True)


def preload() -> None:
    """
    edge-tts streams from the cloud on each call — nothing to preload.
    This function exists so main.py can call it unconditionally without
    needing to know which TTS engine is in use.
    """
    logger.info("Edge TTS ready (voice=%s, rate=%s)", EDGE_VOICE, EDGE_RATE)

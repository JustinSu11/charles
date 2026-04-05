"""
stt.py — OpenAI Whisper speech-to-text pipeline.

Whisper runs entirely on the local machine — no audio is ever sent to the cloud.
The model is downloaded automatically on first use and cached in ~/.cache/whisper.

Model selection (via WHISPER_MODEL in .env):

    base   ~140 MB   Fast, good accuracy   (default)
    small  ~460 MB   Slower, better        (~2× more accurate than base)
    medium ~1.5 GB   Slowest, best         (overkill for most command queries)

Whisper expects float32 audio at 16 000 Hz mono, which is exactly what
audio.record_until_silence() returns.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

MODEL_NAME: str = os.getenv("WHISPER_MODEL", "base")

# Language hint.  Set to None to let Whisper auto-detect.
LANGUAGE: Optional[str] = os.getenv("WHISPER_LANGUAGE") or None

# Lazy-load so the heavy torch import only happens when STT is first used.
_whisper_model = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_model():
    """Load (or return cached) Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        import whisper  # heavy import — deferred deliberately
        logger.info("Loading Whisper model '%s'… (first run will download the weights)", MODEL_NAME)
        t0 = time.perf_counter()
        _whisper_model = whisper.load_model(MODEL_NAME)
        logger.info("Whisper model loaded in %.1f s", time.perf_counter() - t0)
    return _whisper_model


# ── Public API ────────────────────────────────────────────────────────────────

def transcribe(audio: np.ndarray) -> str:
    """
    Transcribe a float32 audio array to text using Whisper.

    Parameters
    ----------
    audio
        1-D float32 NumPy array normalised to [-1.0, 1.0] at 16 000 Hz.
        Produced directly by ``audio.record_until_silence()``.

    Returns
    -------
    str
        The transcribed text, stripped of leading/trailing whitespace.
        Returns an empty string if the audio was too short or silent.
    """
    if audio is None or len(audio) < 1600:   # < 0.1 s → treat as empty
        logger.debug("Audio too short for transcription (%d samples)", len(audio) if audio is not None else 0)
        return ""

    model = _load_model()

    decode_kwargs: dict = {}
    if LANGUAGE:
        decode_kwargs["language"] = LANGUAGE

    logger.info("Transcribing %.1f s of audio with Whisper '%s'…", len(audio) / 16_000, MODEL_NAME)
    t0 = time.perf_counter()
    
    result = model.transcribe(audio, fp16=False, **decode_kwargs)

    text: str = result.get("text", "").strip()
    elapsed = time.perf_counter() - t0
    logger.info("Transcription (%.2f s): %r", elapsed, text)

    # Whisper hallucinates multilingual garbage on near-silence — discard it.
    # If more than 30% of characters are non-ASCII the output is not real speech.
    if text:
        non_ascii = sum(1 for c in text if ord(c) > 127)
        if non_ascii / len(text) > 0.30:
            logger.info("Transcription discarded — likely hallucination (%.0f%% non-ASCII)", 100 * non_ascii / len(text))
            return ""

    return text


def transcribe_file(path: str) -> str:
    """
    Convenience wrapper — transcribe a WAV/MP3/etc. file from disk.

    Useful for testing without a live microphone.
    """
    import whisper  # noqa: F401 — ensure import works before loading
    model = _load_model()
    result = model.transcribe(path, fp16=False)
    return result.get("text", "").strip()


def preload_model() -> None:
    """
    Explicitly trigger model download / load.

    Call this at startup (before the wake word loop starts) so the first voice
    interaction doesn't have a multi-second delay waiting for Whisper to load.
    """
    _load_model()

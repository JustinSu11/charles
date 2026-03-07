"""
wake_word.py — Porcupine multi-keyword wake word detection.

Porcupine runs on-device (no network call) with very low CPU overhead.
It processes 16 kHz mono audio in fixed-size frames and fires a callback
when ANY of the loaded wake words are detected.

Multiple wake words
-------------------
Drop any number of .ppn model files into voice/models/ and all are loaded
simultaneously.  Porcupine fires on whichever one it hears first.

Recommended setup — generate both of these at https://console.picovoice.ai/ppn
(select your OS platform for each):

    voice/models/hey-charles.ppn   ← "Hey Charles"
    voice/models/charles.ppn       ← "Charles"

Sensitivity
-----------
WAKE_WORD_SENSITIVITY in .env applies to all models uniformly (0.0–1.0).
To set per-model sensitivities, set WAKE_WORD_SENSITIVITIES as a comma-
separated list in the same order that models are discovered (alphabetical):
    WAKE_WORD_SENSITIVITIES=0.5,0.6

Fallback
--------
If no .ppn files exist the detector falls back to Picovoice's built-in
"porcupine" keyword so the service still starts during development.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import pvporcupine
from dotenv import load_dotenv

from audio import MicrophoneStream, CHUNK

load_dotenv()
logger = logging.getLogger(__name__)

# ── Paths / env ───────────────────────────────────────────────────────────────

_VOICE_DIR = Path(__file__).parent
_MODELS_DIR = _VOICE_DIR / "models"

ACCESS_KEY: str = os.getenv("PICOVOICE_ACCESS_KEY", "")

# Default sensitivity applied to every model unless overridden.
SENSITIVITY: float = float(os.getenv("WAKE_WORD_SENSITIVITY", "0.5"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _discover_models() -> list[Path]:
    """Return all .ppn files in voice/models/, sorted alphabetically."""
    if not _MODELS_DIR.exists():
        return []
    return sorted(_MODELS_DIR.glob("*.ppn"))


def _keyword_label(path: Path) -> str:
    """Derive a human-readable label from a .ppn filename, e.g. 'hey-charles'."""
    return path.stem  # strips .ppn extension


def _build_sensitivities(count: int) -> list[float]:
    """
    Build a per-model sensitivity list.

    Reads WAKE_WORD_SENSITIVITIES (comma-separated) first; falls back to
    repeating WAKE_WORD_SENSITIVITY for all models.
    """
    raw = os.getenv("WAKE_WORD_SENSITIVITIES", "")
    if raw:
        parts = [s.strip() for s in raw.split(",") if s.strip()]
        if len(parts) >= count:
            return [float(p) for p in parts[:count]]
        # Pad with the default if not enough values were provided
        return [float(p) for p in parts] + [SENSITIVITY] * (count - len(parts))
    return [SENSITIVITY] * count


# ── Public API ────────────────────────────────────────────────────────────────

def wait_for_wake_word(
    on_detected: Optional[Callable[[str], None]] = None,
    input_device_index: Optional[int] = None,
    stop_event=None,          # threading.Event — set it to exit the loop
) -> str:
    """
    Block until any configured wake word is detected, then return.

    Auto-discovers every .ppn file in voice/models/ and loads them all
    simultaneously — so "Hey Charles", "Charles", or any other variant you
    generate will all trigger the same callback.

    Parameters
    ----------
    on_detected
        Optional callback invoked immediately on detection (before returning).
        Receives the label of the matched keyword (e.g. ``'charles'``).
        Useful for lighting up a status indicator from the launcher.
    input_device_index
        Microphone device index.  None → system default.
    stop_event
        A ``threading.Event``.  When set, the loop exits without detection.

    Returns
    -------
    str
        The label of the keyword that triggered (e.g. ``'hey-charles'`` or
        ``'charles'``).  Returns ``'unknown'`` on fallback keywords.
    """
    if not ACCESS_KEY:
        raise EnvironmentError(
            "PICOVOICE_ACCESS_KEY is not set. "
            "Sign up at https://console.picovoice.ai/ and add the key to your .env file."
        )

    ppn_paths = _discover_models()

    if ppn_paths:
        keyword_labels = [_keyword_label(p) for p in ppn_paths]
        sensitivities = _build_sensitivities(len(ppn_paths))
        logger.info(
            "Wake word models loaded: %s (sensitivities: %s)",
            ", ".join(keyword_labels),
            ", ".join(f"{s:.2f}" for s in sensitivities),
        )
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=[str(p) for p in ppn_paths],
            sensitivities=sensitivities,
        )
    else:
        # Fallback: use two built-in keywords as stand-ins during development
        logger.warning(
            "No .ppn files found in %s. "
            "Falling back to built-in 'porcupine' keyword for testing. "
            "Generate 'Hey Charles' and 'Charles' models at https://console.picovoice.ai/ppn "
            "and place them in voice/models/",
            _MODELS_DIR,
        )
        keyword_labels = ["porcupine (fallback)"]
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=["porcupine"],
            sensitivities=[SENSITIVITY],
        )

    logger.info(
        "Listening for: %s  (frame_length=%d, sample_rate=%d)",
        " | ".join(keyword_labels),
        porcupine.frame_length,
        porcupine.sample_rate,
    )

    try:
        with MicrophoneStream(input_device_index=input_device_index) as mic:
            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.info("stop_event set — exiting wake word loop")
                    return "stopped"

                pcm_bytes = mic.read_frame()

                # Porcupine expects a list of 16-bit signed ints, one per sample
                pcm = list(
                    int.from_bytes(pcm_bytes[i : i + 2], byteorder="little", signed=True)
                    for i in range(0, len(pcm_bytes), 2)
                )

                result = porcupine.process(pcm)
                if result >= 0:
                    label = keyword_labels[result] if result < len(keyword_labels) else "unknown"
                    logger.info("Wake word detected: '%s'", label)
                    if on_detected:
                        on_detected(label)
                    return label

    finally:
        porcupine.delete()


def run_forever(
    on_wake: Callable[[], None],
    input_device_index: Optional[int] = None,
    stop_event=None,
    model_path: Optional[Path] = None,  # kept for backward compat, ignored
) -> None:
    """
    Repeatedly call *on_wake* each time any wake word is detected.

    This is a convenience wrapper around ``wait_for_wake_word`` for use cases
    where you want to re-arm detection after each interaction (i.e. main.py).

    Parameters
    ----------
    on_wake
        Callback invoked every time a wake word fires.  The callback should
        be **blocking** (handle the full voice interaction) so that detection
        is paused while Charles is speaking or processing.
    stop_event
        Set to exit the loop cleanly between detections.
    """
    models = _discover_models()
    if models:
        labels = " | ".join(_keyword_label(p) for p in models)
        logger.info("Wake word loop started — listening for: %s", labels)
    else:
        logger.info("Wake word loop started — listening for: porcupine (fallback)")
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            wait_for_wake_word(
                input_device_index=input_device_index,
                stop_event=stop_event,
            )
            if stop_event is not None and stop_event.is_set():
                break
            on_wake()
        except Exception as exc:
            logger.error("Wake word loop error: %s — restarting in 2 s", exc, exc_info=True)
            time.sleep(2)

    logger.info("Wake word loop exited")

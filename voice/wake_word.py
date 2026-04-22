"""
wake_word.py — OpenWakeWord multi-model wake word detection.

OpenWakeWord is a fully open-source, Apache-2.0-licensed wake word engine.
No API key or account required.

Multiple wake words
-------------------
Place any number of .onnx model files in voice/models/ and all are loaded
simultaneously.  OpenWakeWord fires on whichever model scores above the
threshold first.

Recommended setup — place trained .onnx files here:

    voice/models/hey-charles.onnx   ← "Hey Charles"
    voice/models/charles.onnx       ← "Charles" (optional variant)

See documentation/adding-openwakeword-model.md for instructions.

Fallback
--------
If no .onnx files are found, the detector falls back to the built-in
'hey_jarvis' model so the service still starts during development or before
a custom "Hey Charles" model has been trained.

Threshold
---------
WAKE_WORD_THRESHOLD in .env sets the detection threshold (0.0–1.0).
Higher values = fewer false positives but may miss quiet detections.
Default: 0.5
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from dotenv import load_dotenv
import openwakeword
from openwakeword.model import Model

from audio import MicrophoneStream

load_dotenv()
logger = logging.getLogger(__name__)

# ── Paths / env ───────────────────────────────────────────────────────────────

_VOICE_DIR = Path(__file__).parent
_MODELS_DIR = _VOICE_DIR / "models"

# Detection threshold applied to every loaded model (0.0–1.0).
THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# OpenWakeWord requires 1280-sample frames (80 ms at 16 kHz).
# audio.py uses CHUNK=512, so frames are accumulated here without touching
# the shared audio pipeline.
_OWW_FRAME_SAMPLES = 1280


# ── OWW internal model names — never treated as wake word models ──────────────
# OpenWakeWord's preprocessing pipeline requires melspectrogram.onnx and
# embedding_model.onnx.  These live inside the openwakeword package resources
# directory, but some distributions / manual installs place them elsewhere.
# We explicitly exclude them so _discover_models never picks them up by accident.
_OWW_INTERNAL_MODELS = {"melspectrogram", "embedding_model"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_oww_models() -> None:
    """
    Download OpenWakeWord's internal preprocessing models if not already present.

    OWW requires melspectrogram.onnx and embedding_model.onnx in its resource
    directory before any Model() can be instantiated.  Calling download_models()
    is a no-op if the files already exist.
    """
    try:
        openwakeword.utils.download_models()
    except Exception as exc:
        logger.warning("Could not download OWW preprocessing models: %s", exc)


def _discover_models() -> list[Path]:
    """Return wake-word .onnx files in voice/models/, excluding OWW internals."""
    if not _MODELS_DIR.exists():
        return []
    return sorted(
        p for p in _MODELS_DIR.glob("*.onnx")
        if p.stem not in _OWW_INTERNAL_MODELS
    )


def _load_oww_model(onnx_paths: list[Path]) -> Model:
    """Load an OpenWakeWord model from .onnx files, or fall back to hey_jarvis."""
    if onnx_paths:
        logger.info(
            "Wake word models loaded: %s",
            ", ".join(p.stem for p in onnx_paths),
        )
        return Model(
            wakeword_models=[str(p) for p in onnx_paths],
            inference_framework="onnx",
        )
    # Fallback: use a built-in model during development / before custom model exists
    logger.warning(
        "No .onnx models found in %s — falling back to built-in 'hey_jarvis' for testing. "
        "See documentation/adding-openwakeword-model.md to add a custom wake word.",
        _MODELS_DIR,
    )
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


# ── Public API ────────────────────────────────────────────────────────────────

def wait_for_wake_word(
    on_detected: Optional[Callable[[str], None]] = None,
    input_device_index: Optional[int] = None,
    stop_event=None,          # threading.Event — set it to exit the loop
    on_ready: Optional[Callable[[], None]] = None,
) -> str:
    """
    Block until any configured wake word is detected, then return.

    Auto-discovers every .onnx file in voice/models/ and loads them all
    simultaneously — so "Hey Charles", "Charles", or any other variant you
    add will all trigger the same callback.

    Parameters
    ----------
    on_detected
        Optional callback invoked immediately on detection (before returning).
        Receives the model name of the matched keyword (e.g. ``'hey_charles'``).
        Useful for lighting up a status indicator from the launcher.
    input_device_index
        Microphone device index.  None → system default.
    stop_event
        A ``threading.Event``.  When set, the loop exits without detection.
    on_ready
        Optional callback invoked once the microphone is open and the
        detection loop is about to start.  Use this to emit STANDBY state
        only when the service is genuinely ready to hear the wake word —
        not before model loading and mic initialisation complete.

    Returns
    -------
    str
        The model name that triggered (e.g. ``'hey_charles'``).
        Returns ``'stopped'`` if stop_event was set before detection.
    """
    _ensure_oww_models()
    onnx_paths = _discover_models()
    if onnx_paths:
        logger.info("Found wake word models in %s: %s", _MODELS_DIR, [p.name for p in onnx_paths])
    else:
        logger.info("No .onnx models found in %s", _MODELS_DIR)
    oww = _load_oww_model(onnx_paths)
    buffer: list[int] = []

    logger.info(
        "Listening for: %s  (threshold=%.2f, frame=%d samples)",
        " | ".join(oww.models.keys()),
        THRESHOLD,
        _OWW_FRAME_SAMPLES,
    )

    with MicrophoneStream(input_device_index=input_device_index) as mic:
        # Mic is open and OWW is loaded — signal to the caller that we are
        # genuinely ready to detect the wake word now.
        if on_ready is not None:
            on_ready()

        while True:
            if stop_event is not None and stop_event.is_set():
                logger.info("stop_event set — exiting wake word loop")
                return "stopped"

            pcm_bytes = mic.read_frame()

            # Convert raw bytes to a list of signed 16-bit ints
            samples = [
                int.from_bytes(pcm_bytes[i : i + 2], byteorder="little", signed=True)
                for i in range(0, len(pcm_bytes), 2)
            ]
            buffer.extend(samples)

            # Process complete 1280-sample frames; keep the remainder buffered
            while len(buffer) >= _OWW_FRAME_SAMPLES:
                frame = np.array(buffer[:_OWW_FRAME_SAMPLES], dtype=np.int16)
                buffer = buffer[_OWW_FRAME_SAMPLES:]
                scores: dict[str, float] = oww.predict(frame)

                # Emit debug telemetry so the launcher can display mic level
                # and per-model scores in real time.
                rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)) / 32767)
                parts = [f"rms={rms:.4f}"] + [f"{n}={s:.4f}" for n, s in scores.items()]
                print(f"VOICE_DEBUG:{','.join(parts)}", flush=True)

                for name, score in scores.items():
                    if score >= THRESHOLD:
                        logger.info("Wake word detected: '%s' (score=%.3f)", name, score)
                        if on_detected:
                            on_detected(name)
                        return name


def run_forever(
    on_wake: Callable[[], None],
    input_device_index: Optional[int] = None,
    stop_event=None,
    on_ready: Optional[Callable[[], None]] = None,
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
    on_ready
        Forwarded to ``wait_for_wake_word`` on every arm/re-arm cycle.
        Called each time the mic is open and genuinely listening — including
        after a conversation ends and detection re-arms.
    """
    models = _discover_models()
    if models:
        labels = " | ".join(p.stem for p in models)
        logger.info("Wake word loop started — listening for: %s", labels)
    else:
        logger.info("Wake word loop started — listening for: hey_jarvis (fallback)")

    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            wait_for_wake_word(
                input_device_index=input_device_index,
                stop_event=stop_event,
                on_ready=on_ready,
            )
            if stop_event is not None and stop_event.is_set():
                break
            on_wake()
        except Exception as exc:
            logger.error("Wake word loop error: %s — restarting in 2 s", exc, exc_info=True)
            time.sleep(2)

    logger.info("Wake word loop exited")

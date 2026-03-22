"""
tts.py — Piper text-to-speech pipeline.

Piper is a local, offline neural TTS engine.  It ships as a standalone binary
that reads text from stdin and writes a WAV file to stdout.

Binary location (relative to this file):
    Windows : voice/bin/piper.exe
    macOS   : voice/bin/piper
    Linux   : voice/bin/piper

Voice model (ONNX + JSON config):
    voice/models/en_US-lessac-medium.onnx          (or whichever you chose)
    voice/models/en_US-lessac-medium.onnx.json

Both the binary and models auto-download on first run via `_ensure_assets()`.

Voices are sourced from https://huggingface.co/rhasspy/piper-voices

Environment variables:
    PIPER_VOICE   — model name without extension (default: en_US-lessac-medium)
    PIPER_RATE    — playback speed [0.5 – 2.0]   (default: 1.0)
"""

from __future__ import annotations

import io
import logging
import os
import platform
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from audio import play_wav_bytes

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_VOICE_DIR = Path(__file__).parent
_BIN_DIR = _VOICE_DIR / "bin"
_MODELS_DIR = _VOICE_DIR / "models"

PIPER_VOICE: str = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
PIPER_RATE: float = float(os.getenv("PIPER_RATE", "1.0"))

# Piper binary name per platform
_PIPER_BINARY: str = "piper.exe" if platform.system() == "Windows" else "piper"
# The piper release zip extracts into a 'piper/' subdirectory inside _BIN_DIR
# e.g.  voice/bin/piper/piper.exe  (not  voice/bin/piper.exe)
PIPER_BIN: Path = _BIN_DIR / "piper" / _PIPER_BINARY

# Hugging Face base URL for model downloads
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# ── Auto-download assets ──────────────────────────────────────────────────────

def _hf_voice_url(voice: str, filename: str) -> str:
    """
    Build a Hugging Face URL for a piper-voices model file.

    Piper voice names follow the pattern:  {lang}_{country}-{name}-{quality}
    e.g.  en_US-lessac-medium → en/en_US/lessac/medium/
    """
    parts = voice.split("-")          # ["en_US", "lessac", "medium"]
    lang_country = parts[0]           # "en_US"
    lang = lang_country.split("_")[0] # "en"
    name = parts[1] if len(parts) > 1 else "default"
    quality = parts[2] if len(parts) > 2 else "medium"
    path = f"{lang}/{lang_country}/{name}/{quality}/{filename}"
    return f"{_HF_BASE}/{path}"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s → %s", url, dest)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    logger.info("Downloaded %s", dest.name)


def _ensure_assets() -> None:
    """
    Download the Piper binary and voice model if they are not already present.

    Users can also download manually and skip this step — see voice/README.md.
    """
    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Binary ───────────────────────────────────────────────────────────────
    if not PIPER_BIN.exists():
        system = platform.system()
        machine = platform.machine().lower()

        # Map to Piper release asset names
        asset_map = {
            ("Windows", "amd64"): "piper_windows_amd64.zip",
            ("Windows", "x86_64"): "piper_windows_amd64.zip",
            ("Darwin", "arm64"): "piper_macos_aarch64.tar.gz",
            ("Darwin", "x86_64"): "piper_macos_x86_64.tar.gz",
            ("Linux", "aarch64"): "piper_linux_aarch64.tar.gz",
            ("Linux", "arm64"): "piper_linux_aarch64.tar.gz",
            ("Linux", "x86_64"): "piper_linux_x86_64.tar.gz",
            ("Linux", "amd64"): "piper_linux_x86_64.tar.gz",
        }
        asset = asset_map.get((system, machine))
        if asset is None:
            raise RuntimeError(
                f"No pre-built Piper binary for {system}/{machine}. "
                "Download manually from https://github.com/rhasspy/piper/releases "
                f"and place the binary at {PIPER_BIN}"
            )

        release_url = f"https://github.com/rhasspy/piper/releases/latest/download/{asset}"
        archive_path = _BIN_DIR / asset
        _download(release_url, archive_path)

        # Extract
        if asset.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(archive_path) as z:
                z.extractall(_BIN_DIR)
        else:
            import tarfile
            with tarfile.open(archive_path) as t:
                t.extractall(_BIN_DIR)

        archive_path.unlink(missing_ok=True)

        # Make executable on Unix
        if system != "Windows":
            PIPER_BIN.chmod(0o755)

        logger.info("Piper binary ready at %s", PIPER_BIN)

    # ── Voice model ──────────────────────────────────────────────────────────
    onnx_path = _MODELS_DIR / f"{PIPER_VOICE}.onnx"
    json_path = _MODELS_DIR / f"{PIPER_VOICE}.onnx.json"

    if not onnx_path.exists():
        _download(_hf_voice_url(PIPER_VOICE, f"{PIPER_VOICE}.onnx"), onnx_path)

    if not json_path.exists():
        _download(_hf_voice_url(PIPER_VOICE, f"{PIPER_VOICE}.onnx.json"), json_path)


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
        The text to synthesise.  Markdown and special characters are passed
        through — Piper handles most punctuation gracefully.
    output_device_index
        Speaker device index.  None → system default.
    """
    if not text or not text.strip():
        return

    _stop_playback.clear()

    try:
        _ensure_assets()
    except Exception as exc:
        logger.error("Could not ensure Piper assets: %s", exc)
        return

    onnx_path = _MODELS_DIR / f"{PIPER_VOICE}.onnx"

    cmd: list[str] = [
        str(PIPER_BIN),
        "--model", str(onnx_path),
        "--output-raw",             # raw PCM stdout (we wrap it in WAV ourselves)
        "--sentence-silence", "0.2",
    ]

    if PIPER_RATE != 1.0:
        cmd += ["--length-scale", str(1.0 / PIPER_RATE)]  # Piper uses length-scale (inverse of rate)

    logger.info("Speaking: %r", text[:80])

    with _playback_lock:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Feed text to piper, read raw PCM output
            stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=30)

            if proc.returncode != 0:
                logger.error("Piper error: %s", stderr.decode(errors="replace"))
                return

            if _stop_playback.is_set():
                logger.debug("TTS playback aborted before it started")
                return

            # Piper --output-raw produces headerless 16-bit mono PCM at the
            # model's native sample rate (usually 22 050 Hz).  Wrap it in a
            # WAV header so play_wav_bytes() can handle it.
            wav_bytes = _pcm_to_wav(stdout, sample_rate=22_050, channels=1, sample_width=2)
            play_wav_bytes(wav_bytes, output_device_index=output_device_index)

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Piper timed out")
        except Exception as exc:
            logger.error("TTS error: %s", exc, exc_info=True)


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    """Wrap raw PCM bytes in a RIFF/WAV header."""
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def preload() -> None:
    """
    Ensure the Piper binary and voice model are downloaded at startup.

    Call this before the first ``speak()`` so the first voice interaction
    doesn't stall on a download.
    """
    try:
        _ensure_assets()
        logger.info("Piper TTS assets ready (voice=%s)", PIPER_VOICE)
    except Exception as exc:
        logger.error("Failed to preload Piper assets: %s", exc)

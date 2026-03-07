"""
audio.py — Audio device enumeration, capture buffer, and silence detection.

Responsibilities:
- List available microphone and speaker devices
- Record audio from the microphone into a NumPy array
- Detect end-of-speech via energy-based silence detection
- Provide a helper to play raw PCM audio through the speakers

Cross-platform:
  Windows  → WASAPI (pyaudio selects automatically)
  macOS    → CoreAudio (pyaudio selects automatically)
  Linux    → ALSA / PulseAudio (pyaudio selects automatically)
"""

from __future__ import annotations

import os
import time
import wave
import io
import struct
import logging
from typing import Optional

import numpy as np
import pyaudio

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_RATE: int = 16_000          # Hz — Whisper and Porcupine both expect 16 kHz
CHANNELS: int = 1                   # Mono
SAMPLE_WIDTH: int = 2               # 16-bit PCM → 2 bytes per sample
CHUNK: int = 512                    # Frames per PyAudio buffer read (Porcupine frame size)

# Silence detection defaults (can be overridden in .env)
DEFAULT_SILENCE_THRESHOLD: float = float(os.getenv("SILENCE_THRESHOLD", "500"))    # RMS amplitude
DEFAULT_SILENCE_DURATION: float = float(os.getenv("SILENCE_DURATION_S", "1.5"))   # Seconds of silence before stopping
DEFAULT_MAX_RECORD_SECONDS: float = float(os.getenv("MAX_RECORD_SECONDS", "30"))  # Hard upper limit


# ── Device helpers ────────────────────────────────────────────────────────────

def list_devices() -> list[dict]:
    """
    Return a list of all available PyAudio audio devices.

    Each dict has keys:
        index, name, max_input_channels, max_output_channels, default_sample_rate
    """
    pa = pyaudio.PyAudio()
    devices = []
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            devices.append({
                "index": i,
                "name": info["name"],
                "max_input_channels": info["maxInputChannels"],
                "max_output_channels": info["maxOutputChannels"],
                "default_sample_rate": info["defaultSampleRate"],
            })
    finally:
        pa.terminate()
    return devices


def list_input_devices() -> list[dict]:
    """Return only devices that have at least one input channel (microphones)."""
    return [d for d in list_devices() if d["max_input_channels"] > 0]


def list_output_devices() -> list[dict]:
    """Return only devices that have at least one output channel (speakers)."""
    return [d for d in list_devices() if d["max_output_channels"] > 0]


def get_default_input_index() -> Optional[int]:
    """Return the system default input device index, or None if none exists."""
    try:
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            return int(info["index"])
        finally:
            pa.terminate()
    except OSError:
        return None


def get_default_output_index() -> Optional[int]:
    """Return the system default output device index, or None if none exists."""
    try:
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_output_device_info()
            return int(info["index"])
        finally:
            pa.terminate()
    except OSError:
        return None


# ── Porcupine-compatible frame reader ────────────────────────────────────────

class MicrophoneStream:
    """
    An always-open PyAudio input stream yielding 16-bit PCM frames at CHUNK
    samples each.  Designed to be used by wake_word.py in its detection loop.

    Usage::

        with MicrophoneStream(input_device_index=None) as mic:
            for frame in mic:
                # frame is bytes of length CHUNK * SAMPLE_WIDTH
                ...
    """

    def __init__(self, input_device_index: Optional[int] = None) -> None:
        self._device_index = input_device_index
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None

    def __enter__(self) -> "MicrophoneStream":
        self._pa = pyaudio.PyAudio()
        kwargs: dict = dict(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        if self._device_index is not None:
            kwargs["input_device_index"] = self._device_index

        self._stream = self._pa.open(**kwargs)
        self._stream.start_stream()
        logger.debug("MicrophoneStream opened (device=%s)", self._device_index)
        return self

    def __exit__(self, *_) -> None:
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()
        logger.debug("MicrophoneStream closed")

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        if self._stream is None:
            raise StopIteration
        return self._stream.read(CHUNK, exception_on_overflow=False)

    def read_frame(self) -> bytes:
        """Read exactly one CHUNK-sized frame (blocking)."""
        return next(self)


# ── Speech capture (post wake-word) ──────────────────────────────────────────

def _rms(frame: bytes) -> float:
    """Compute the root-mean-square amplitude of a 16-bit PCM frame."""
    count = len(frame) // SAMPLE_WIDTH
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", frame)
    mean_sq = sum(s * s for s in shorts) / count
    return mean_sq ** 0.5


def record_until_silence(
    input_device_index: Optional[int] = None,
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
    silence_duration: float = DEFAULT_SILENCE_DURATION,
    max_duration: float = DEFAULT_MAX_RECORD_SECONDS,
) -> np.ndarray:
    """
    Record audio from the microphone until the user stops speaking.

    Silence detection: once the RMS amplitude drops below *silence_threshold*
    for *silence_duration* consecutive seconds, recording stops.

    Returns a float32 NumPy array of shape (N,) normalised to [-1.0, 1.0],
    which is exactly what openai-whisper expects.

    Parameters
    ----------
    input_device_index
        Pass None to use the system default microphone.
    silence_threshold
        RMS energy below which audio is considered silent (default 500).
    silence_duration
        Seconds of continuous silence that signals end-of-speech (default 1.5).
    max_duration
        Hard upper limit in seconds before recording stops regardless (default 30).
    """
    pa = pyaudio.PyAudio()
    kwargs: dict = dict(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )
    if input_device_index is not None:
        kwargs["input_device_index"] = input_device_index

    stream = pa.open(**kwargs)
    stream.start_stream()

    frames: list[bytes] = []
    silent_chunks = 0
    silence_chunk_limit = int(silence_duration * SAMPLE_RATE / CHUNK)
    max_chunks = int(max_duration * SAMPLE_RATE / CHUNK)

    logger.info("Recording… (silence threshold=%.0f, max=%.0fs)", silence_threshold, max_duration)

    try:
        for _ in range(max_chunks):
            frame = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(frame)
            if _rms(frame) < silence_threshold:
                silent_chunks += 1
                if silent_chunks >= silence_chunk_limit:
                    logger.debug("Silence detected — stopping recording")
                    break
            else:
                silent_chunks = 0
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames:
        return np.zeros(0, dtype=np.float32)

    # Convert 16-bit PCM bytes → float32 in [-1.0, 1.0]
    raw = b"".join(frames)
    audio_int16 = np.frombuffer(raw, dtype=np.int16)
    return audio_int16.astype(np.float32) / 32768.0


# ── Playback ──────────────────────────────────────────────────────────────────

def play_wav_bytes(wav_bytes: bytes, output_device_index: Optional[int] = None) -> None:
    """
    Play raw WAV-format bytes through the speakers.

    Piper TTS outputs WAV data to stdout; pass those bytes directly here.

    Parameters
    ----------
    wav_bytes
        Complete WAV file as bytes (including the RIFF header).
    output_device_index
        Pass None to use the system default output device.
    """
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        sample_width = wf.getsampwidth()
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pa.get_format_from_width(sample_width),
            channels=n_channels,
            rate=framerate,
            output=True,
            output_device_index=output_device_index,
        )
        try:
            chunk = 1024
            data = wf.readframes(chunk)
            while data:
                stream.write(data)
                data = wf.readframes(chunk)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

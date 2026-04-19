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
import threading
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
    pre_speech_timeout: Optional[float] = None,
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
    pre_speech_timeout
        If set, give up and return an empty array if no speech above
        *silence_threshold* is detected within this many seconds.  Useful
        for conversation mode: exit the loop if the user doesn't respond.
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
    speech_started = False
    silence_chunk_limit = int(silence_duration * SAMPLE_RATE / CHUNK)
    max_chunks = int(max_duration * SAMPLE_RATE / CHUNK)
    pre_speech_chunk_limit = (
        int(pre_speech_timeout * SAMPLE_RATE / CHUNK) if pre_speech_timeout is not None else None
    )

    logger.info("Recording… (silence threshold=%.0f, max=%.0fs)", silence_threshold, max_duration)

    try:
        for chunk_index in range(max_chunks):
            frame = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(frame)
            if _rms(frame) >= silence_threshold:
                speech_started = True
                silent_chunks = 0
            else:
                # Pre-speech timeout: give up if user hasn't spoken yet
                if not speech_started and pre_speech_chunk_limit is not None:
                    if chunk_index >= pre_speech_chunk_limit:
                        logger.debug("Pre-speech timeout — no speech detected, exiting")
                        return np.zeros(0, dtype=np.float32)
                silent_chunks += 1
                if speech_started and silent_chunks >= silence_chunk_limit:
                    logger.debug("Silence detected — stopping recording")
                    break
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


# ── Thinking chime ───────────────────────────────────────────────────────────

def _make_tone(freq: float, duration_ms: int, sample_rate: int = 24_000,
               amplitude: float = 0.35) -> np.ndarray:
    """
    Generate a single sine-wave tone with a short fade-in and fade-out.

    Returns a float32 array normalised to [-1.0, 1.0].
    The fade prevents clicking at the start/end of each note.
    """
    n = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n, endpoint=False)
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32)

    # 10 ms fade-in / fade-out to avoid clicks
    fade_n = min(int(sample_rate * 0.01), n // 4)
    fade_in  = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
    fade_out = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
    wave[:fade_n]  *= fade_in
    wave[-fade_n:] *= fade_out

    return wave * amplitude


def _pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int = 24_000) -> bytes:
    """Convert a float32 numpy array to WAV bytes (16-bit mono)."""
    pcm = (samples * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def play_wake_chime(output_device_index: Optional[int] = None) -> None:
    """
    Play a soft 2-tone rising chime immediately when the wake word fires.

    Gives the user instant audio confirmation that Charles heard them —
    before the TTS ack phrase ("Yes?") has time to generate.
    Two tones: E5 (660 Hz) → A5 (880 Hz), upward motion, warm not sharp.
    """
    SR = 24_000
    try:
        lo = _make_tone(660, 110, SR, amplitude=0.25)
        silence = np.zeros(int(SR * 0.020), dtype=np.float32)
        hi = _make_tone(880, 160, SR, amplitude=0.25)
        chime = np.concatenate([lo, silence, hi])
        play_wav_bytes(_pcm_to_wav_bytes(chime, SR), output_device_index=output_device_index)
    except Exception as exc:
        logger.debug("Wake chime failed: %s", exc)


def play_processing_loop(
    stop_event: threading.Event,
    output_device_index: Optional[int] = None,
) -> None:
    """
    Play a very soft repeating pulse while Charles is waiting for the API response.

    Runs in a background thread — caller sets stop_event to end playback.
    Each cycle: 80 ms tone + 120 ms silence = 200 ms period.
    Kept very quiet (amplitude 0.10) so it doesn't compete with speech.
    """
    SR = 24_000
    pulse = _pcm_to_wav_bytes(_make_tone(440, 80, SR, amplitude=0.10), SR)
    silence_ms = 120
    silence_samples = int(SR * silence_ms / 1000)

    while not stop_event.is_set():
        try:
            play_wav_bytes(pulse, output_device_index=output_device_index)
        except Exception as exc:
            logger.debug("Processing loop pulse failed: %s", exc)
            break
        # Sleep for the silence gap in small increments so stop_event is checked promptly
        deadline = time.monotonic() + silence_ms / 1000
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return
            time.sleep(0.02)


def play_thinking_chime(output_device_index: Optional[int] = None) -> None:
    """
    Play a soft, warm pad tone to signal that Charles is processing.

    Designed to be subtle and non-intrusive — a single note built from
    layered harmonics (fundamental + 2nd + 3rd) with a slow fade-in and
    long decay, similar to ChatGPT's processing sound.

    The tone is quiet and round rather than sharp — the user hears
    "I got that" without being startled.
    """
    SR = 24_000
    FREQ = 520.0          # just above C5 — warm, readable on laptop speakers
    DURATION_MS = 380
    n = int(SR * DURATION_MS / 1000)
    t = np.linspace(0, DURATION_MS / 1000, n, endpoint=False, dtype=np.float32)

    # Layer harmonics for a round, pad-like timbre instead of a thin sine beep
    fundamental = np.sin(2 * np.pi * FREQ * t)
    harmonic2   = np.sin(2 * np.pi * FREQ * 2 * t) * 0.30
    harmonic3   = np.sin(2 * np.pi * FREQ * 3 * t) * 0.12
    tone = (fundamental + harmonic2 + harmonic3).astype(np.float32)

    # Smooth envelope: slow attack (~25% of duration), then exponential decay
    attack_n = int(n * 0.25)
    envelope = np.ones(n, dtype=np.float32)
    envelope[:attack_n] = np.linspace(0.0, 1.0, attack_n)
    # Exponential decay over the remaining 75%
    decay_n = n - attack_n
    envelope[attack_n:] = np.exp(-3.5 * np.linspace(0, 1, decay_n)).astype(np.float32)

    tone = tone * envelope * 0.22   # keep it subtle — low master amplitude

    try:
        play_wav_bytes(_pcm_to_wav_bytes(tone, SR), output_device_index=output_device_index)
    except Exception as exc:
        logger.debug("Thinking chime failed: %s", exc)


# ── Playback ──────────────────────────────────────────────────────────────────

def play_wav_bytes(
    wav_bytes: bytes,
    output_device_index: Optional[int] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    Play raw WAV-format bytes through the speakers.

    Piper TTS outputs WAV data to stdout; pass those bytes directly here.

    Parameters
    ----------
    wav_bytes
        Complete WAV file as bytes (including the RIFF header).
    output_device_index
        Pass None to use the system default output device.
    stop_event
        Optional ``threading.Event``.  When set, playback stops cleanly
        after the current chunk finishes — used for barge-in and wake-word
        interruption mid-sentence.
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
                if stop_event and stop_event.is_set():
                    break
                stream.write(data)
                data = wf.readframes(chunk)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

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
import queue
import re
import struct
import threading
import time
import wave
from typing import Optional

import edge_tts
import miniaudio

from audio import play_wav_bytes, SAMPLE_RATE, CHUNK, DEFAULT_SILENCE_THRESHOLD

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

EDGE_VOICE: str  = os.getenv("EDGE_VOICE",  "en-GB-RyanNeural")
EDGE_RATE: str   = os.getenv("EDGE_RATE",   "+0%")
EDGE_VOLUME: str = os.getenv("EDGE_VOLUME", "+0%")
EDGE_PITCH: str  = os.getenv("EDGE_PITCH",  "-10Hz")  # negative = deeper; sweet spot: -5Hz to -15Hz

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
_playback_done = threading.Event()


def stop_speaking() -> None:
    """
    Signal that the current TTS playback should abort.

    Call this from the wake word callback so that detecting "Hey Charles"
    mid-sentence immediately stops Charles and listens again.
    """
    _stop_playback.set()


# ── Barge-in detection ────────────────────────────────────────────────────────

# Barge-in is disabled by default because speaker audio bleeds into the
# microphone and can exceed the energy threshold, causing Charles to interrupt
# his own TTS playback.  Enable only after you have tuned BARGE_IN_THRESHOLD
# high enough that speaker bleed does NOT trigger detection.
#
# To enable: add  BARGE_IN_ENABLED=true  to your .env file, then raise
# BARGE_IN_THRESHOLD until false triggers stop (try 2500–4000).
BARGE_IN_ENABLED: bool = os.getenv("BARGE_IN_ENABLED", "false").lower() in ("1", "true", "yes")

# Higher than the normal recording threshold because the microphone picks up
# some bleed from the speakers during playback.  Only relevant when enabled.
BARGE_IN_THRESHOLD: float = float(os.getenv("BARGE_IN_THRESHOLD", "2500"))

# Consecutive chunks above threshold required before we declare a barge-in.
# 5 chunks × 512 samples / 16 000 Hz ≈ 160 ms — long enough to ignore clicks.
_BARGE_IN_SUSTAIN: int = 5

# Post-trigger silence chunks before capture stops (≈ 1.5 s).
_BARGE_IN_SILENCE: int = int(1.5 * SAMPLE_RATE / CHUNK)

# Single-slot queue: barge-in monitor deposits captured audio here;
# main._one_turn() picks it up before opening a fresh mic stream.
_barge_in_queue: queue.Queue = queue.Queue(maxsize=1)


def _mic_rms(frame: bytes) -> float:
    """RMS amplitude of a 16-bit PCM frame — mirrors audio._rms."""
    count = len(frame) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", frame)
    return (sum(s * s for s in shorts) / count) ** 0.5


def _barge_in_monitor(input_device_index: Optional[int]) -> None:
    """
    Run in a background thread during TTS playback.

    Opens the microphone and monitors energy level.  If sustained speech
    above BARGE_IN_THRESHOLD is detected:
      1. Calls stop_speaking() to interrupt playback immediately.
      2. Continues recording until silence, then deposits the audio in
         _barge_in_queue so the conversation loop can transcribe it
         without the user having to repeat themselves.

    Exits automatically when _playback_done is set (normal playback end)
    without having been triggered.
    """
    # Lazy imports — keep pyaudio initialisation out of module load time so
    # it cannot affect the asyncio event loop used by edge-tts in the main thread.
    import numpy as np
    import pyaudio as _pa_mod

    pa = _pa_mod.PyAudio()
    kwargs: dict = dict(
        format=_pa_mod.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )
    if input_device_index is not None:
        kwargs["input_device_index"] = input_device_index

    try:
        stream = pa.open(**kwargs)
        stream.start_stream()
    except Exception as exc:
        logger.warning("Barge-in monitor could not open mic: %s", exc)
        pa.terminate()
        return

    # Rolling pre-roll buffer so we capture the beginning of the utterance
    # even before the sustain check fires.
    pre_roll: list[bytes] = []
    post_frames: list[bytes] = []
    sustained: int = 0
    triggered: bool = False
    silent_chunks: int = 0

    try:
        while True:
            # Check the stop condition before attempting a read.
            # If playback finished and we were never triggered, exit cleanly.
            if _playback_done.is_set() and not triggered:
                return

            # Non-blocking poll: only read when a full chunk is ready.
            # This prevents stream.read() from blocking indefinitely, which
            # would delay the _playback_done check above by up to one frame.
            if stream.get_read_available() < CHUNK:
                time.sleep(0.01)
                continue

            frame = stream.read(CHUNK, exception_on_overflow=False)
            rms = _mic_rms(frame)

            if not triggered:
                # Keep a short pre-roll so the start of the utterance isn't cut off
                pre_roll.append(frame)
                if len(pre_roll) > _BARGE_IN_SUSTAIN + 4:
                    pre_roll.pop(0)

                if rms >= BARGE_IN_THRESHOLD:
                    sustained += 1
                    if sustained >= _BARGE_IN_SUSTAIN:
                        triggered = True
                        stop_speaking()
                        logger.info("Barge-in detected (RMS %.0f) — interrupting TTS", rms)
                else:
                    sustained = 0
            else:
                # Post-trigger: capture until natural silence
                post_frames.append(frame)
                if rms < DEFAULT_SILENCE_THRESHOLD:
                    silent_chunks += 1
                    if silent_chunks >= _BARGE_IN_SILENCE:
                        break
                else:
                    silent_chunks = 0
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if triggered:
        all_frames = pre_roll + post_frames
        if all_frames:
            raw = b"".join(all_frames)
            audio_int16 = np.frombuffer(raw, dtype=np.int16)
            audio_f32 = audio_int16.astype(np.float32) / 32768.0
            try:
                _barge_in_queue.put_nowait(audio_f32)
                logger.info("Barge-in audio captured (%d frames → %.1f s)",
                            len(all_frames), len(all_frames) * CHUNK / SAMPLE_RATE)
            except queue.Full:
                logger.debug("Barge-in queue full — discarding audio")


def get_barge_in_audio() -> Optional[np.ndarray]:
    """
    Return audio captured by the barge-in monitor, or None.

    Called by main._one_turn() before opening a fresh microphone stream.
    If barge-in audio is available the caller should use it directly and
    skip record_until_silence() so the user does not need to repeat themselves.
    """
    try:
        return _barge_in_queue.get_nowait()
    except queue.Empty:
        return None


# ── Audio generation ──────────────────────────────────────────────────────────

async def _generate_mp3(text: str) -> bytes:
    """Stream audio from edge-tts and return the full MP3 bytes."""
    communicate = edge_tts.Communicate(text, voice=EDGE_VOICE, rate=EDGE_RATE, volume=EDGE_VOLUME, pitch=EDGE_PITCH)
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
    input_device_index: Optional[int] = None,
    barge_in: bool = False,
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
    input_device_index
        Microphone device index for barge-in monitoring.  None → system default.
        Only relevant when ``barge_in=True``.
    barge_in
        When True, a background thread monitors the microphone during playback.
        If the user starts speaking, playback stops immediately and the captured
        audio is made available via ``get_barge_in_audio()``.  Default False —
        only enable for substantive replies, not short ack/error phrases.
    """
    if not text or not text.strip():
        return

    _stop_playback.clear()
    _playback_done.clear()
    clean = _clean_for_tts(text)

    if not clean:
        return

    logger.info("Speaking: %r", clean[:80])

    with _playback_lock:
        monitor_thread: Optional[threading.Thread] = None
        try:
            mp3_bytes = asyncio.run(_generate_mp3(clean))

            if _stop_playback.is_set():
                logger.debug("TTS playback aborted before it started")
                return

            wav_bytes = _mp3_to_wav(mp3_bytes)

            # Only start the barge-in monitor for full replies and only when
            # the feature is explicitly enabled (opt-in to avoid speaker bleed
            # false-triggering on default hardware setups).
            if barge_in and BARGE_IN_ENABLED:
                monitor_thread = threading.Thread(
                    target=_barge_in_monitor,
                    args=(input_device_index,),
                    daemon=True,
                    name="barge-in-monitor",
                )
                monitor_thread.start()

            play_wav_bytes(
                wav_bytes,
                output_device_index=output_device_index,
                stop_event=_stop_playback,
            )

        except Exception as exc:
            logger.error("TTS error: %s", exc, exc_info=True)
        finally:
            # Signal the monitor that playback has ended (triggered or not).
            _playback_done.set()
            # Wait for the monitor to finish capturing the barge-in utterance.
            # Timeout of 8 s covers the longest expected spoken response.
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=8.0)


def preload() -> None:
    """
    edge-tts streams from the cloud on each call — nothing to preload.
    This function exists so main.py can call it unconditionally without
    needing to know which TTS engine is in use.
    """
    logger.info("Edge TTS ready (voice=%s, rate=%s, pitch=%s)", EDGE_VOICE, EDGE_RATE, EDGE_PITCH)

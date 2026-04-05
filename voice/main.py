"""
main.py — Charles voice service entry point.

Starts the always-on wake word loop.  When "Hey Charles" is detected:
  1. Plays an acknowledgement chime / phrase
  2. Records the user's command (silence-gated)
  3. Transcribes with Whisper (local STT)
  4. Sends the text to the Charles API
  5. Speaks the reply with Piper TTS

Usage
-----
    python main.py [--input-device N] [--output-device N] [--list-devices]

Environment variables (all optional — see .env.example):
    PICOVOICE_ACCESS_KEY   Required for wake word detection
    WHISPER_MODEL          base | small | medium  (default: base)
    PIPER_VOICE            Piper voice model name  (default: en_US-lessac-medium)
    CHARLES_API_URL        http://localhost:8000
    SILENCE_THRESHOLD      RMS amplitude cutoff    (default: 500)
    SILENCE_DURATION_S     Seconds of silence before stop (default: 1.5)
    WAKE_WORD_SENSITIVITY  0.0–1.0  (default: 0.5)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from dotenv import load_dotenv

# ── Load .env before importing our modules (they read env at import time) ──────
load_dotenv()

import api_client
import audio
import stt
import tts
import wake_word

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("charles.voice")

# ── Acknowledgement phrases (spoken after wake word fires) ────────────────────

ACK_PHRASES = [
    "Yes?",
    "I'm listening.",
    "Go ahead.",
    "How can I help?",
]
_ack_index = 0


def _ack_phrase() -> str:
    global _ack_index
    phrase = ACK_PHRASES[_ack_index % len(ACK_PHRASES)]
    _ack_index += 1
    return phrase


# ── Stop phrases — saying any of these ends the conversation ─────────────────

_STOP_PHRASES = frozenset((
    "goodbye", "bye", "stop", "that's all", "stop listening",
    "never mind", "exit", "go away",
))

# Seconds to wait for speech after Charles stops speaking.
# If the user is quiet for this long, the conversation ends and the
# service returns to wake word mode.
_CONVERSATION_TIMEOUT_S: float = float(os.getenv("CONVERSATION_TIMEOUT_S", "8"))


# ── Single interaction turn ───────────────────────────────────────────────────

def _one_turn(
    input_device_index: Optional[int],
    output_device_index: Optional[int],
    pre_speech_timeout: Optional[float] = None,
) -> str:
    """
    Execute one listen → transcribe → respond cycle.

    Parameters
    ----------
    pre_speech_timeout
        Passed to ``audio.record_until_silence``.  None means "wait as long
        as needed" (used for the first turn right after wake word).  A positive
        number means "give up if the user hasn't spoken within this many
        seconds" (used for follow-up turns in conversation mode).

    Returns
    -------
    "continue"  — turn completed normally; stay in conversation mode.
    "stop"      — user said a stop phrase; exit conversation mode.
    "timeout"   — no speech detected; exit conversation mode silently.
    """
    print("VOICE_STATE:LISTENING", flush=True)
    logger.info("Waiting for user to speak…")

    # Brief pause so the new PyAudio input stream has time to initialise.
    # Without this, the first ~150ms of speech is lost because the stream
    # isn't ready when the user starts speaking right after the ack phrase.
    time.sleep(0.2)

    audio_data = audio.record_until_silence(
        input_device_index=input_device_index,
        pre_speech_timeout=pre_speech_timeout,
    )

    if audio_data is None or len(audio_data) < 1600:
        return "timeout"

    print("VOICE_STATE:TRANSCRIBING", flush=True)
    text = stt.transcribe(audio_data)

    if not text:
        logger.info("Transcription was empty")
        tts.speak("Sorry, I didn't catch that.", output_device_index=output_device_index)
        return "continue"

    logger.info("User said: %r", text)
    lower = text.lower().strip()

    # Stop phrases — end the conversation
    if any(k in lower for k in _STOP_PHRASES):
        tts.speak("Goodbye!", output_device_index=output_device_index)
        return "stop"

    # Special local commands (no API round-trip needed)
    if any(k in lower for k in ("new conversation", "start over", "reset", "forget that")):
        api_client.reset_conversation()
        tts.speak("Starting a new conversation.", output_device_index=output_device_index)
        return "continue"

    # Emit transcript immediately so the GUI can show it before the API responds
    print(f"VOICE_TRANSCRIPT:{text}", flush=True)

    # Send to Charles API
    reply = api_client.send_message(text)

    # Speak reply (interruptible via wake word — stop_speaking() is called
    # by the wake word thread if the user says "Hey Charles" mid-reply)
    print("VOICE_STATE:SPEAKING", flush=True)
    tts.speak(reply, output_device_index=output_device_index)

    return "continue"


# ── Core interaction loop ─────────────────────────────────────────────────────

def handle_wake(
    input_device_index: Optional[int],
    output_device_index: Optional[int],
    stop_event: threading.Event,
) -> None:
    """
    Called each time the wake word is detected.

    Handles the first turn then stays in conversation mode — the user
    can keep talking without saying the wake word again.  The conversation
    ends when:
      • the user says a stop phrase ("goodbye", "stop", etc.)
      • the user is silent for CONVERSATION_TIMEOUT_S seconds
      • stop_event is set (voice service shutting down)
    """
    # Acknowledge
    ack = _ack_phrase()
    logger.info("Wake word detected — acknowledging: %r", ack)
    tts.speak(ack, output_device_index=output_device_index)

    # First turn: no pre-speech timeout — user just triggered the wake word
    result = _one_turn(input_device_index, output_device_index, pre_speech_timeout=None)

    if result == "timeout":
        tts.speak("I didn't hear anything. Say 'Hey Charles' when you're ready.",
                  output_device_index=output_device_index)
        print("VOICE_STATE:STANDBY", flush=True)
        return

    if result == "stop":
        print("VOICE_STATE:STANDBY", flush=True)
        return

    # Conversation loop: stay active until silence timeout or stop phrase
    logger.info("Entering conversation mode — listening for follow-up…")
    while not stop_event.is_set():
        result = _one_turn(
            input_device_index,
            output_device_index,
            pre_speech_timeout=_CONVERSATION_TIMEOUT_S,
        )
        if result in ("stop", "timeout"):
            if result == "timeout":
                logger.info("Conversation timed out — returning to wake word mode")
            break

    logger.info("Conversation ended (reason: %s)", result)
    print("VOICE_STATE:STANDBY", flush=True)


# ── Startup ───────────────────────────────────────────────────────────────────

def startup_checks() -> bool:
    """
    Verify the environment and pre-download heavy assets.
    Returns False if a critical requirement is missing.
    """
    ok = True

    # API reachability
    logger.info("Checking Charles API at %s …", api_client.API_BASE_URL)
    if api_client.health_check():
        logger.info("Charles API is healthy")
    else:
        logger.warning(
            "Charles API is not reachable at %s. "
            "Voice interactions will fail until the Docker containers are running. "
            "Start them with: docker compose up -d",
            api_client.API_BASE_URL,
        )
        # Non-fatal: wake word still starts, errors will be spoken back

    # Pre-download Piper binary + voice model
    logger.info("Pre-loading Piper TTS assets…")
    tts.preload()

    # Pre-load Whisper model (avoids first-turn delay)
    logger.info("Pre-loading Whisper model '%s'…", stt.MODEL_NAME)
    try:
        stt.preload_model()
    except Exception as exc:
        logger.error("Failed to load Whisper: %s", exc)
        ok = False

    return ok


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Charles voice service — always-on wake word assistant",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio input/output devices and exit.",
    )
    p.add_argument(
        "--input-device",
        type=int,
        default=None,
        metavar="N",
        help="Microphone device index (default: system default).",
    )
    p.add_argument(
        "--output-device",
        type=int,
        default=None,
        metavar="N",
        help="Speaker device index (default: system default).",
    )
    p.add_argument(
        "--no-preload",
        action="store_true",
        help="Skip pre-loading Whisper and Piper on startup (faster start, slower first turn).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --list-devices
    if args.list_devices:
        print("\n=== Input devices (microphones) ===")
        for d in audio.list_input_devices():
            default = " [DEFAULT]" if d["index"] == audio.get_default_input_index() else ""
            print(f"  [{d['index']:2d}] {d['name']}{default}")
        print("\n=== Output devices (speakers) ===")
        for d in audio.list_output_devices():
            default = " [DEFAULT]" if d["index"] == audio.get_default_output_index() else ""
            print(f"  [{d['index']:2d}] {d['name']}{default}")
        print()
        sys.exit(0)

    logger.info("=== Charles Voice Service starting ===")

    if not args.no_preload:
        startup_checks()

    # Graceful shutdown on Ctrl+C / SIGTERM
    stop_event = threading.Event()

    def _shutdown(sig, frame):
        logger.info("Shutdown signal received — stopping…")
        tts.stop_speaking()
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    input_dev = args.input_device
    output_dev = args.output_device

    logger.info(
        "Ready. Microphone: %s, Speaker: %s",
        f"device {input_dev}" if input_dev is not None else "system default",
        f"device {output_dev}" if output_dev is not None else "system default",
    )
    print("VOICE_STATE:STANDBY", flush=True)

    # Listen for INTERRUPT commands from Electron via stdin (non-blocking thread)
    def _stdin_listener():
        try:
            for line in sys.stdin:
                if line.strip().upper() == "INTERRUPT":
                    logger.info("Interrupt received from GUI")
                    tts.stop_speaking()
                    print("VOICE_STATE:STANDBY", flush=True)
        except Exception:
            pass  # stdin closed on shutdown — expected
    threading.Thread(target=_stdin_listener, daemon=True).start()

    # Wrap handle_wake so wake_word.run_forever() can call it without arguments
    def _on_wake():
        # If the wake word fires while Charles is speaking, interrupt playback
        tts.stop_speaking()
        time.sleep(0.1)   # brief pause so the speaker buffer flushes
        if not stop_event.is_set():
            handle_wake(
                input_device_index=input_dev,
                output_device_index=output_dev,
                stop_event=stop_event,
            )

    # Run the wake word loop (blocks until stop_event is set)
    try:
        wake_word.run_forever(
            on_wake=_on_wake,
            input_device_index=input_dev,
            stop_event=stop_event,
        )
    except EnvironmentError as exc:
        # Missing PICOVOICE_ACCESS_KEY
        logger.critical("%s", exc)
        sys.exit(1)

    logger.info("Charles Voice Service stopped.")


if __name__ == "__main__":
    main()

# Sequence Diagram 6 of 7 — Barge-In Interruption

Covers: the barge-in monitor that runs during TTS playback, how it captures user speech mid-reply, and how that audio is reused in the next turn. Only active when BARGE_IN_ENABLED=true in .env.

```mermaid
sequenceDiagram
    actor User
    participant Mic as MicrophoneStream<br>(audio.py)
    participant TTS as Edge TTS<br>(tts.py)
    participant Main as VoiceMain<br>(main.py)
    participant STT as Whisper STT<br>(stt.py)
    participant UI as Electron UI<br>(renderer)

    Note over TTS: speak(reply, barge_in=True) called

    TTS ->> TTS: start _barge_in_monitor()<br>background thread
    TTS -->> User: audio playback begins

    par TTS plays reply audio
        TTS -->> User: streaming MP3 → WAV → PyAudio
    and Barge-in monitor watches mic
        loop Monitor loop
            Mic -->> TTS: read mic energy (RMS)
            Note over TTS: Threshold: BARGE_IN_THRESHOLD<br>(default 2500 RMS)
        end
    end

    User ->> Mic: speaks mid-reply
    TTS ->> TTS: energy spike >= BARGE_IN_THRESHOLD
    TTS ->> TTS: stop_speaking() — set _stop_event
    TTS ->> TTS: record user speech into capture buffer
    TTS ->> TTS: store captured audio in barge-in queue

    TTS -->> UI: (playback stops)
    Main -->> UI: VOICE_STATE:LISTENING

    Main ->> TTS: get_barge_in_audio()
    TTS -->> Main: captured float32 audio array
    Note over Main: Skips opening a new mic stream<br>Uses captured audio directly in next _one_turn()

    Main ->> STT: transcribe(barge_in_audio)
    STT -->> Main: transcribed text
    Note over Main: Conversation continues<br>without user repeating themselves
```

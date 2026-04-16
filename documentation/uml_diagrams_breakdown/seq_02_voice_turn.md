# Sequence Diagram 2 of 7 — Voice Turn (STT → API → TTS)

Covers: recording the user's speech, transcription, sending to the API, receiving a reply, and speaking it back. Skill routing detail is in seq_03–05.

```mermaid
sequenceDiagram
    actor User
    participant Mic as MicrophoneStream<br>(audio.py)
    participant Main as VoiceMain<br>(main.py)
    participant STT as Whisper STT<br>(stt.py)
    participant Chat as POST /chat<br>(chat.py)
    participant DB as SQLite DB
    participant OR as OpenRouter API<br>(external)
    participant WS as WebSocket Manager<br>(ws_manager.py)
    participant TTS as Edge TTS<br>(tts.py)
    participant UI as Electron UI<br>(renderer)

    Note over Main,Mic: Continues from seq_01 after wake word detected

    Main ->> Mic: record_until_silence()
    User ->> Mic: speaks command
    Mic -->> Main: float32 audio array
    Main -->> UI: VOICE_STATE:TRANSCRIBING

    Main ->> STT: transcribe(audio_data)
    Note over STT: Runs locally via Whisper<br>No network call
    STT -->> Main: transcribed text string
    Main -->> UI: VOICE_TRANSCRIPT: text

    par Thinking chime
        Main ->> TTS: play_thinking_chime()
        TTS -->> User: chime audio (~470 ms)
    and API call
        Main ->> Chat: POST /chat<br>{message, interface:"voice"}
        Chat ->> DB: get or create shared conversation
        DB -->> Chat: conversation_id
        Chat ->> DB: fetch message history (ordered by created_at)
        DB -->> Chat: history rows
        Chat ->> DB: INSERT user message
        Chat ->> DB: SELECT active_model from app_state
        Note over Chat: Skill routing runs here<br>(see seq_03 / seq_04 / seq_05)
        Chat ->> OR: HTTPS POST /api/v1/chat/completions<br>{history + system_prompt + skill_context, model}
        OR -->> Chat: assistant reply text
        Chat ->> DB: INSERT assistant message
        Chat ->> WS: broadcast {type:"turn", user, assistant}
        WS -->> UI: WebSocket push → renders turn bubble
        Chat -->> Main: ChatResponse {response}
    end

    Main -->> UI: VOICE_STATE:SPEAKING
    Main ->> TTS: speak(reply, barge_in=True)
    TTS -->> User: audio playback
    Note over Main: Barge-in detail in seq_06<br>Conversation loop repeats _one_turn()<br>until stop phrase or 8 s timeout
    Main -->> UI: VOICE_STATE:STANDBY
```

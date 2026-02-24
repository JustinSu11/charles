# voice/

Native Python voice service for Charles — runs on the host machine so it can access audio devices directly.

## What goes here

- `main.py` — Entry point; starts the always-on wake word loop
- `wake_word.py` — Porcupine integration ("Hey Charles" detection)
- `stt.py` — Whisper speech-to-text pipeline (microphone → text)
- `tts.py` — Piper text-to-speech pipeline (text → speakers)
- `audio.py` — Audio device enumeration, capture buffer, silence detection
- `api_client.py` — HTTP client that sends transcribed text to `POST /chat`
- `requirements.txt` — Python dependencies (see below)

## Setup

### 1. Install Python dependencies

```bash
cd voice
pip install -r requirements.txt
```

### 2. Install Piper TTS binary

Download the binary for your platform from https://github.com/rhasspy/piper/releases and place it at:

- Windows: `voice/bin/piper.exe`
- macOS/Linux: `voice/bin/piper`

### 3. Generate wake word model

1. Sign up at https://console.picovoice.ai/
2. Create a custom "Hey Charles" wake word for your target platform
3. Download the `.ppn` file and place it at `voice/models/hey-charles.ppn`

### 4. Configure environment

Copy `../.env.example` to `../.env` and fill in your `PICOVOICE_ACCESS_KEY`.

### 5. Run

```bash
python main.py
```

## Audio pipeline

```
Microphone
    │
    ▼
pvporcupine (wake word "Hey Charles")
    │  detected
    ▼
PyAudio capture buffer + silence detection
    │
    ▼
openai-whisper (STT — local, offline)
    │  transcribed text
    ▼
POST /chat  →  Charles API  →  OpenRouter  →  response text
    │
    ▼
piper-tts (TTS — local, offline)
    │
    ▼
Speakers
```

## Platform notes

| Platform | Audio backend   | Known issues                                                   |
| -------- | --------------- | -------------------------------------------------------------- |
| Windows  | WASAPI          | May need `pipwin install pyaudio` if wheel fails               |
| macOS    | CoreAudio       | `brew install portaudio` required before `pip install pyaudio` |
| Linux    | ALSA/PulseAudio | `sudo apt-get install portaudio19-dev` required                |

## Whisper model selection

| Model  | Size   | Speed (CPU) | Accuracy |
| ------ | ------ | ----------- | -------- |
| base   | 140 MB | ~1×         | Good     |
| small  | 460 MB | ~0.5×       | Better   |
| medium | 1.5 GB | ~0.2×       | Best     |

Default: `base`. Override with `WHISPER_MODEL=small` in `.env`.

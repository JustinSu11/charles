# voice/

Native Python voice service for Charles — runs on the host machine so it can access audio devices directly.

## What goes here

- `main.py` — Entry point; starts the always-on wake word loop
- `wake_word.py` — OpenWakeWord integration (local, no API key required)
- `stt.py` — Whisper speech-to-text pipeline (microphone → text)
- `tts.py` — Edge TTS text-to-speech pipeline (text → speakers)
- `audio.py` — Audio device enumeration, capture buffer, silence detection
- `api_client.py` — HTTP client that sends transcribed text to `POST /chat`
- `requirements.txt` — Python dependencies (see below)

## Setup

### 1. Install Python dependencies

```bash
cd voice
pip install -r requirements.txt
```

### 2. Add a wake word model (optional)

By default Charles listens for **"Hey Jarvis"** using a built-in OpenWakeWord model — no setup needed. To use a custom wake phrase (e.g. "Hey Charles"), place an `.onnx` model file in `voice/models/`:

```
voice/models/hey-charles.onnx
```

See [documentation/adding-openwakeword-model.md](../documentation/adding-openwakeword-model.md) for full instructions.

### 3. Configure environment

Copy `../.env.example` to `../.env` and fill in your `OPENROUTER_API_KEY`.

Optionally tune the wake word detection threshold (default `0.5`):

```
WAKE_WORD_THRESHOLD=0.5
```

### 4. Run

```bash
python main.py
```

## Audio pipeline

```
Microphone
    │
    ▼
OpenWakeWord (wake word — local, no API key)
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
edge-tts (TTS — Microsoft Azure Neural voices)
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

## Wake word threshold tuning

OpenWakeWord returns a confidence score (0.0–1.0) for each model on every audio frame. Detection fires when the score exceeds `WAKE_WORD_THRESHOLD`.

| Value | Effect |
| ----- | ------ |
| `0.3` | More sensitive — fewer missed detections, more false positives |
| `0.5` | Default — balanced |
| `0.7` | Less sensitive — fewer false positives, may miss quiet speech |

Adjust in `.env` if Charles triggers too often or not often enough in your environment.

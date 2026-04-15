# Charles — Architecture Diagram

```mermaid
graph TB

    subgraph User["👤 User"]
        MIC["Microphone"]
        SPK["Speakers"]
        KBD["Keyboard / Mouse"]
    end

    subgraph Electron["Electron Desktop App (launcher/)"]
        direction TB
        MAIN["main.js — Main Process<br>─────────────────────<br>Window + tray management<br>Subprocess lifecycle<br>Port 8000 cleanup on start<br>IPC routing"]
        PRELOAD["preload.js — Context Bridge<br>─────────────────────<br>Exposes electronAPI<br>onVoiceDebug / onVoiceState<br>onVoiceTranscript / onStatusUpdate"]
        RENDERER["renderer/index.html — Chat UI<br>─────────────────────<br>Message bubbles (voice + web)<br>Voice state pill<br>Audio debug panel (mic level,<br>per-model OWW scores)<br>Model selector"]
        WIZARD["wizard.js + wizard.html<br>─────────────────────<br>Python version check<br>pip install (api + voice)<br>OpenRouter key entry<br>VirusTotal key entry (optional)"]

        MAIN <-->|IPC invoke / send| PRELOAD
        PRELOAD <-->|contextBridge| RENDERER
        MAIN -->|spawns on first run| WIZARD
    end

    subgraph VoiceService["Python Voice Service (voice/)"]
        direction TB
        VMAIN["main.py — Entry Point<br>─────────────────────<br>Startup checks + preload<br>Wake word loop<br>Conversation mode<br>Emits: VOICE_STATE:*<br>Emits: VOICE_DEBUG:*<br>Emits: VOICE_TRANSCRIPT:*<br>Reads: INTERRUPT from stdin"]
        WAKE["wake_word.py — Wake Word<br>─────────────────────<br>OpenWakeWord (local ONNX)<br>_ensure_oww_models() on start<br>Scans voice/models/*.onnx<br>Fallback: hey_jarvis built-in<br>1280-sample frame accumulation<br>RMS debug telemetry per frame"]
        AUDIO["audio.py — Audio I/O<br>─────────────────────<br>MicrophoneStream (PyAudio)<br>CHUNK=512 @ 16kHz mono<br>record_until_silence()<br>RMS silence detection"]
        STT["stt.py — Speech-to-Text<br>─────────────────────<br>OpenAI Whisper (local)<br>float32 audio → text<br>Hallucination filter"]
        TTS["tts.py — Text-to-Speech<br>─────────────────────<br>edge-tts (Microsoft Neural)<br>Barge-in monitor thread<br>MP3 → WAV → PyAudio"]
        APICLI["api_client.py — HTTP Client<br>─────────────────────<br>POST /chat<br>conversation_id state<br>health_check()"]
        MODELS["voice/models/<br>─────────────────────<br>*.onnx (custom wake phrases)<br>e.g. hey-charles.onnx"]

        VMAIN --> WAKE
        VMAIN --> STT
        VMAIN --> TTS
        VMAIN --> APICLI
        VMAIN --> AUDIO
        WAKE --> AUDIO
        WAKE --> MODELS
    end

    subgraph APIService["FastAPI Backend (api/) — 127.0.0.1:8000"]
        direction TB
        FASTAPI["app/main.py — FastAPI<br>─────────────────────<br>GET /health<br>Lifespan: DB table init"]

        subgraph Routers["Routers (app/routers/)"]
            CHAT["POST /chat<br>──────────<br>1. Resolve conversation<br>2. Fetch history<br>3. Store user msg<br>4. Route to skills<br>5. Call OpenRouter<br>6. Store assistant msg<br>7. WS broadcast"]
            HISTORY["GET /history/{id}<br>GET /history/shared<br>DELETE /history/{id}"]
            SETTINGS["GET /settings/model<br>PUT /settings/model<br>GET /models"]
            WSROUTER["WS /ws<br>Real-time turn push"]
        end

        subgraph Services["Services (app/services/)"]
            CONV["conversation.py<br>──────────<br>get_or_create_shared<br>fetch_history<br>store_message"]
            WSMGR["ws_manager.py<br>──────────<br>ConnectionManager<br>broadcast(payload)"]
            SKILLR["skill_router.py<br>──────────<br>route(message)<br>Tier 1/2/3 keyword<br>matching per skill"]
            ORSERVICE["openrouter.py<br>──────────<br>System prompt builder<br>Voice brevity prompt<br>Skill context injection<br>HTTPS POST → OpenRouter"]
        end

        subgraph Skills["Skills (app/skills/)"]
            SVTSKILL["virustotal.py<br>──────────<br>Extract hash or URL<br>HTTPS GET → VT API v3<br>_verdict() + _top_labels()<br>Requires: VIRUSTOTAL_API_KEY"]
            SCVESKILL["cve.py<br>──────────<br>Date-range CVE fetch<br>HTTPS GET → NVD API 2.0<br>CVSS severity sort<br>Optional: NVD_API_KEY"]
            SNEWSSKILL["tech_news.py<br>──────────<br>Top story IDs fetch<br>Parallel item fetches<br>No auth required"]
        end

        DB[("SQLite DB<br>~/.charles/charles.db<br>─────────────────────<br>conversations (id, interface)<br>messages (id, conv_id, role, content)<br>app_state (key, value)")]

        FASTAPI --> Routers
        CHAT --> CONV
        CHAT --> SKILLR
        CHAT --> ORSERVICE
        CHAT --> WSMGR
        HISTORY --> CONV
        SETTINGS --> DB
        WSROUTER --> WSMGR
        SKILLR --> SVTSKILL
        SKILLR --> SCVESKILL
        SKILLR --> SNEWSSKILL
        CONV --> DB
    end

    subgraph ExternalAPIs["External APIs"]
        OR["OpenRouter<br>openrouter.ai/api/v1<br>─────────────────────<br>POST /chat/completions<br>Auth: Bearer token<br>Models: DeepSeek, GPT-4o,<br>Claude, Llama, etc.<br>Requires: OPENROUTER_API_KEY"]
        EDGETSS["Microsoft Edge TTS<br>─────────────────────<br>WebSocket synthesis<br>text → MP3 stream<br>No auth required"]
        VTAPI["VirusTotal API v3<br>virustotal.com/api/v3<br>─────────────────────<br>GET /files/{hash}<br>GET /urls/{base64url}<br>Auth: x-apikey header<br>Free: 500 req/day<br>Requires: VIRUSTOTAL_API_KEY"]
        NVDAPI["NVD API 2.0<br>services.nvd.nist.gov<br>─────────────────────<br>GET /rest/json/cves/2.0<br>Params: pubStartDate/End<br>Free (unkeyed): 5 req/30s<br>Optional: NVD_API_KEY<br>Keyed: 50 req/30s"]
        HNAPI["Hacker News API<br>hacker-news.firebaseio.com<br>─────────────────────<br>GET /v0/topstories.json<br>GET /v0/item/{id}.json<br>No auth required"]
        OWWDL["OpenWakeWord CDN<br>─────────────────────<br>melspectrogram.onnx<br>embedding_model.onnx<br>Downloaded once on first run"]
    end

    %% User ↔ Hardware
    MIC -->|PCM audio| AUDIO
    TTS -->|WAV audio| SPK
    KBD -->|text input| RENDERER

    %% Electron ↔ Voice subprocess
    MAIN -->|spawn python voice/main.py| VMAIN
    VMAIN -->|stdout: VOICE_STATE / VOICE_DEBUG / VOICE_TRANSCRIPT| MAIN
    MAIN -->|stdin: INTERRUPT| VMAIN

    %% Electron ↔ API subprocess
    MAIN -->|spawn python api/main.py| FASTAPI
    RENDERER <-->|HTTP REST| FASTAPI
    RENDERER <-->|WebSocket /ws| WSROUTER

    %% Voice → API
    APICLI -->|POST /chat| CHAT

    %% API Skills → External
    SVTSKILL -->|HTTPS GET| VTAPI
    SCVESKILL -->|HTTPS GET| NVDAPI
    SNEWSSKILL -->|HTTPS GET| HNAPI
    ORSERVICE -->|HTTPS POST| OR

    %% TTS → External
    TTS -->|WebSocket text| EDGETSS
    EDGETSS -->|MP3 stream| TTS

    %% OWW download (first run only)
    WAKE -.->|first run: download_models()| OWWDL
    OWWDL -.->|preprocessing models| WAKE

    %% Styles
    style Electron      fill:#1e3a5f,stroke:#2563eb,color:#e8e8e8
    style VoiceService  fill:#2e1065,stroke:#7c3aed,color:#e8e8e8
    style APIService    fill:#14532d,stroke:#16a34a,color:#e8e8e8
    style ExternalAPIs  fill:#1f2937,stroke:#4b5563,color:#e8e8e8
    style User          fill:#0d0d0d,stroke:#374151,color:#e8e8e8
    style DB            fill:#0a0a0a,stroke:#374151,color:#9ca3af
    style MODELS        fill:#0a0a0a,stroke:#374151,color:#9ca3af
    style VTAPI         fill:#450a0a,stroke:#991b1b,color:#fca5a5
    style NVDAPI        fill:#0a1a0a,stroke:#14532d,color:#86efac
    style HNAPI         fill:#1a1200,stroke:#78350f,color:#fcd34d
    style OR            fill:#0a0a1a,stroke:#312e81,color:#a5b4fc
    style EDGETSS       fill:#1a1a1a,stroke:#4b5563,color:#d1d5db
    style OWWDL         fill:#1a1a1a,stroke:#4b5563,color:#d1d5db
```

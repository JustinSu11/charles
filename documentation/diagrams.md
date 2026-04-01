# Charles — System Diagrams

> Generated 2026-03-31. Reflects Phase 1 (backend) + Phase 3 (voice service) implementation.

---

## 1. Use Case Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Charles System                          │
│                                                                 │
│   ┌──────────────────────────────────┐                          │
│   │         Voice Interface          │                          │
│   │                                  │                          │
│   │  ○ Activate with "Hey Charles"   │◄────────────────── 《User》
│   │  ○ Ask a question (voice)        │◄────────────────── 《User》
│   │  ○ Receive spoken reply          │◄────────────────── 《User》
│   │  ○ Interrupt / stop TTS          │◄────────────────── 《User》
│   │  ○ Reset conversation (voice)    │◄────────────────── 《User》
│   └──────────────────────────────────┘                          │
│                                                                 │
│   ┌──────────────────────────────────┐                          │
│   │         Web Interface            │                          │
│   │                                  │                          │
│   │  ○ Chat via Open WebUI           │◄────────────────── 《User》
│   │  ○ Browse conversation history   │◄────────────────── 《User》
│   │  ○ Select AI model               │◄────────────────── 《User》
│   └──────────────────────────────────┘                          │
│                                                                 │
│   ┌──────────────────────────────────┐                          │
│   │         Shared Context           │                          │
│   │                                  │                          │
│   │  ○ Voice + web share one         │                          │
│   │    conversation thread           │                          │
│   └──────────────────────────────────┘                          │
│                                                                 │
│   ┌──────────────────────────────────┐                          │
│   │         System / Admin           │                          │
│   │                                  │                          │
│   │  ○ Start Docker services         │◄────── 《Administrator》  │
│   │  ○ Configure environment (.env)  │◄────── 《Administrator》  │
│   │  ○ Select audio devices (CLI)    │◄────── 《Administrator》  │
│   │  ○ Health check (GET /health)    │◄────── 《Administrator》  │
│   └──────────────────────────────────┘                          │
│                                                                 │
│              ┌────────────────────────┐                         │
│              │     OpenRouter API     │  《External AI Provider》│
│              │  ○ LLM inference       │                         │
│              └────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

**Actors**
| Actor | Description |
|---|---|
| User | Human interacting via voice ("Hey Charles") or browser (Open WebUI) |
| Administrator | Developer configuring the system, managing Docker, setting .env |
| OpenRouter API | External LLM provider (Llama 3.3 70B by default) |

---

## 2. Class Diagram

```mermaid
classDiagram

    %% ── Voice Service Layer (host) ───────────────────────────────────────────

    class VoiceMain {
        +handle_wake(input_dev, output_dev, stop_event)
        +startup_checks() bool
        +main()
        -_ack_phrase() str
        -_shutdown(sig, frame)
    }

    class WakeWord {
        +run_forever(on_wake, input_device_index, stop_event)
        -_porcupine: Porcupine
        -_pa: PyAudio
    }

    class AudioCapture {
        +record_until_silence(input_device_index) bytes
        +list_input_devices() list
        +list_output_devices() list
        +get_default_input_index() int
        +get_default_output_index() int
        -SILENCE_THRESHOLD: int
        -SILENCE_DURATION_S: float
    }

    class STT {
        +transcribe(audio_data: bytes) str
        +preload_model()
        +MODEL_NAME: str
        -_model: WhisperModel
    }

    class TTS {
        +speak(text: str, output_device_index)
        +stop_speaking()
        +preload()
        -_piper_proc: subprocess
        -VOICE: str
    }

    class APIClient {
        +send_message(text: str) str
        +reset_conversation()
        +health_check() bool
        +get_conversation_id() str
        -_conversation_id: str
        -API_BASE_URL: str
        -TIMEOUT: float
    }

    %% ── API Layer (Docker) ───────────────────────────────────────────────────

    class CharlesAPI {
        +POST /chat
        +GET /history/conversation_id
        +DELETE /history/conversation_id
        +GET /health
        +POST /v1/chat/completions
    }

    class ChatRouter {
        +chat(request: ChatRequest, db) ChatResponse
    }

    class HistoryRouter {
        +get_history(conversation_id, db) HistoryResponse
        +delete_history(conversation_id, db)
    }

    class OpenAICompatRouter {
        +chat_completions(request, db)
    }

    class ConversationService {
        +get_or_create_shared_conversation(db) str
        +fetch_history(db, conversation_id) list
        +store_message(db, conversation_id, role, content) str
    }

    class OpenRouterService {
        +get_openrouter_response(history: list) str
        -MODEL: str
        -SYSTEM_PROMPT: str
        -OPENROUTER_API_KEY: str
    }

    %% ── Data Models ──────────────────────────────────────────────────────────

    class ChatRequest {
        +conversation_id: UUID
        +interface: Literal[voice, web]
        +message: str
    }

    class ChatResponse {
        +conversation_id: UUID
        +message_id: UUID
        +response: str
    }

    class MessageOut {
        +id: UUID
        +role: Literal[user, assistant, system]
        +content: str
        +created_at: datetime
    }

    %% ── Database (PostgreSQL) ────────────────────────────────────────────────

    class Conversation {
        <<entity>>
        +id: UUID PK
        +interface: VARCHAR(10)
        +created_at: TIMESTAMPTZ
        +updated_at: TIMESTAMPTZ
    }

    class Message {
        <<entity>>
        +id: UUID PK
        +conversation_id: UUID FK
        +role: VARCHAR(10)
        +content: TEXT
        +created_at: TIMESTAMPTZ
    }

    class AppState {
        <<entity>>
        +key: VARCHAR(100) PK
        +value: TEXT
    }

    %% ── Relationships ────────────────────────────────────────────────────────

    VoiceMain --> WakeWord : listens via
    VoiceMain --> AudioCapture : records via
    VoiceMain --> STT : transcribes via
    VoiceMain --> TTS : speaks via
    VoiceMain --> APIClient : sends text via
    APIClient --> CharlesAPI : HTTP POST /chat

    CharlesAPI --> ChatRouter
    CharlesAPI --> HistoryRouter
    CharlesAPI --> OpenAICompatRouter

    ChatRouter --> ConversationService
    ChatRouter --> OpenRouterService
    HistoryRouter --> ConversationService
    OpenAICompatRouter --> ConversationService
    OpenAICompatRouter --> OpenRouterService

    ConversationService --> Conversation : reads/writes
    ConversationService --> Message : reads/writes
    ConversationService --> AppState : reads/writes shared ID

    ChatRouter ..> ChatRequest : accepts
    ChatRouter ..> ChatResponse : returns
    HistoryRouter ..> MessageOut : returns

    Conversation "1" --> "many" Message : contains
```

---

## 3. Sequence Diagram

> Happy path: User says "Hey Charles, what's a buffer overflow?"

```mermaid
sequenceDiagram
    actor User
    participant WW as WakeWord<br/>(Porcupine)
    participant Main as VoiceMain
    participant Audio as AudioCapture
    participant STT as Whisper STT
    participant TTS as Piper TTS
    participant Client as APIClient
    participant API as CharlesAPI<br/>(FastAPI)
    participant Conv as ConversationService
    participant DB as PostgreSQL
    participant OR as OpenRouter API

    Note over WW: Always-on mic loop

    User->>WW: Says "Hey Charles"
    WW->>Main: on_wake() callback fires
    Main->>TTS: speak("I'm listening.")
    TTS-->>User: Plays acknowledgement audio

    Main->>Audio: record_until_silence()
    User->>Audio: Speaks "What's a buffer overflow?"
    Audio-->>Main: Returns raw PCM bytes

    Main->>STT: transcribe(audio_data)
    STT-->>Main: "What's a buffer overflow?"

    Main->>Client: send_message("What's a buffer overflow?")
    Client->>API: POST /chat {message, interface:"voice"}

    API->>Conv: get_or_create_shared_conversation(db)
    Conv->>DB: SELECT value FROM app_state WHERE key='shared_conversation_id'
    DB-->>Conv: conversation_id (or INSERT new)
    Conv-->>API: conversation_id

    API->>Conv: fetch_history(db, conversation_id)
    Conv->>DB: SELECT role, content FROM messages ORDER BY created_at
    DB-->>Conv: [{role, content}, ...]
    Conv-->>API: conversation history list

    API->>Conv: store_message(db, conversation_id, "user", text)
    Conv->>DB: INSERT INTO messages (user turn)
    DB-->>Conv: message_id

    API->>OR: POST /v1/chat/completions {system_prompt + history}
    OR-->>API: "A buffer overflow is when..."

    API->>Conv: store_message(db, conversation_id, "assistant", reply)
    Conv->>DB: INSERT INTO messages (assistant turn)

    API-->>Client: ChatResponse {conversation_id, message_id, response}
    Client-->>Main: "A buffer overflow is when..."

    Main->>TTS: speak("A buffer overflow is when...")
    TTS-->>User: Plays spoken reply

    Note over WW: Returns to wake word loop

    opt User says "Hey Charles" mid-reply
        User->>WW: "Hey Charles" (interrupts)
        WW->>Main: on_wake() callback
        Main->>TTS: stop_speaking()
        Note over Main: Begins new interaction turn
    end
```

---

## 4. Data Flow Diagram

```
╔══════════════════════════════════════════════════════════════════╗
║                       Level 0 — Context Diagram                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║   [User] ──voice audio──► [         ] ──text reply──► [User]     ║
║   [User] ──web prompt──►  [ CHARLES ] ──text reply──► [User]     ║
║                           [  SYSTEM ]                            ║
║                                ▲                                  ║
║                                │ LLM completions                  ║
║                           [OpenRouter]                            ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════╗
║                     Level 1 — Major Processes                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  [User]                                                           ║
║    │                                                              ║
║    │ raw audio (PCM)                                              ║
║    ▼                                                              ║
║  ┌─────────────────────────────────────────────┐                 ║
║  │  P1: Voice Processing (host)                │                 ║
║  │                                             │                 ║
║  │  Wake Detection ──►  Audio Capture          │                 ║
║  │          ▼                                  │                 ║
║  │    Whisper STT ──► transcribed text ──────► │──────────────┐  ║
║  │                                             │              │  ║
║  │  ◄──────── assistant reply text ──── Piper TTS ◄───────┐  │  ║
║  └─────────────────────────────────────────────┘          │  │  ║
║                                                            │  │  ║
║    │ synthesised audio                                     │  │  ║
║    ▼                                                       │  │  ║
║  [User hears reply]                                        │  │  ║
║                                                            │  │  ║
║  [Browser / Open WebUI]                                    │  │  ║
║    │ text prompt (OpenAI-compat format)                    │  │  ║
║    │                                                       │  │  ║
║    ▼                                                       │  │  ║
║  ┌─────────────────────────────────────────────┐          │  │  ║
║  │  P2: Charles API (Docker, port 8000)        │          │  │  ║
║  │                                             │          │  │  ║
║  │  POST /chat  ◄────────────────────────────────────────────┘  ║
║  │  POST /v1/chat/completions  ◄──────────────────────────────── ║
║  │                     │                       │          │      ║
║  │         ┌───────────▼────────┐              │          │      ║
║  │         │ ConversationService│              │          │      ║
║  │         │  fetch history     │              │          │      ║
║  │         │  store messages    │              │          │      ║
║  │         └───────────┬────────┘              │          │      ║
║  │                     │                       │          │      ║
║  │            read/write messages              │          │      ║
║  │                     ▼                       │          │      ║
║  │         ┌───────────────────┐               │          │      ║
║  │         │  P3: PostgreSQL   │               │          │      ║
║  │         │                   │               │          │      ║
║  │         │  conversations    │               │          │      ║
║  │         │  messages         │               │          │      ║
║  │         │  app_state        │               │          │      ║
║  │         └───────────────────┘               │          │      ║
║  │                                             │          │      ║
║  │  OpenRouterService                          │          │      ║
║  │    history + system_prompt ──────────────────────────────────►║
║  │                                                [OpenRouter]   ║
║  │    ◄──────────────────────────── LLM reply ─────────────────  ║
║  │                                             │          │      ║
║  │  reply ─────────────────────────────────────┘          │      ║
║  │                                             │  reply ──┘      ║
║  └─────────────────────────────────────────────┘                 ║
║                                                                   ║
╠══════════════════════════════════════════════════════════════════╣
║                     Level 2 — Data Stores                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  D1: conversations                                                ║
║      id (UUID), interface (voice|web), created_at, updated_at    ║
║                                                                   ║
║  D2: messages                                                     ║
║      id (UUID), conversation_id (FK→D1), role, content,          ║
║      created_at                                                   ║
║                                                                   ║
║  D3: app_state                                                    ║
║      key='shared_conversation_id' → value=<UUID>                 ║
║      (ensures voice + web always write to the same conversation) ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

### Key Design Decisions Reflected in All Diagrams

| Decision | Rationale |
|---|---|
| Voice service runs on host, not Docker | Docker cannot reliably pass audio hardware through to containers on all platforms |
| Single shared conversation (`app_state`) | Voice and web context is unified — asking via voice then following up in browser works seamlessly |
| `interface` field on every message | Enables future routing logic (e.g., shorter TTS-friendly replies for voice turns) |
| OpenAI-compatible `/v1/chat/completions` route | Open WebUI expects this format — Charles proxies it to OpenRouter without Open WebUI needing a custom integration |
| Conversation history always fetched from DB | Stateless API design — the API holds no in-memory state; all context comes from PostgreSQL |

# Charles — Class Diagram

```mermaid
classDiagram

    %% ── Voice Service ────────────────────────────────────────────────────────

    class MicrophoneStream {
        +int input_device_index
        -PyAudio _pa
        -Stream _stream
        +open()
        +close()
        +read_frame() bytes
    }

    class WakeWordModule {
        +float THRESHOLD
        +int _OWW_FRAME_SAMPLES
        +Path _MODELS_DIR
        -_ensure_oww_models()
        -_discover_models() list~Path~
        -_load_oww_model(onnx_paths) Model
        +wait_for_wake_word(on_detected, input_device_index, stop_event) str
        +run_forever(on_wake, input_device_index, stop_event)
    }

    class STTModule {
        +str MODEL_NAME
        +str LANGUAGE
        -_model
        +preload_model()
        +transcribe(audio_data) str
    }

    class TTSModule {
        +str EDGE_VOICE
        +str EDGE_RATE
        +bool BARGE_IN_ENABLED
        -Event _stop_event
        +preload()
        +speak(text, output_device_index, input_device_index, barge_in)
        +stop_speaking()
        +get_barge_in_audio() ndarray
    }

    class AudioModule {
        +int SAMPLE_RATE
        +int CHUNK
        +int CHANNELS
        +list_input_devices() list
        +list_output_devices() list
        +record_until_silence(input_device_index, pre_speech_timeout) ndarray
        +play_thinking_chime(output_device_index)
        +play_wav_bytes(wav_bytes, output_device_index, stop_event)
    }

    class VoiceAPIClient {
        +str API_BASE_URL
        +str _conversation_id
        +send_message(text) str
        +reset_conversation()
        +health_check() bool
    }

    class VoiceMain {
        +list ACK_PHRASES
        +float _CONVERSATION_TIMEOUT_S
        -_ack_phrase() str
        +startup_checks() bool
        +handle_wake(input_device_index, output_device_index, stop_event)
        -_one_turn(input_device_index, output_device_index, pre_speech_timeout) str
        +main()
    }

    %% ── API Service — Routers ────────────────────────────────────────────────

    class ChatRouter {
        +POST_chat(request, db) ChatResponse
    }

    class HistoryRouter {
        +GET_history_shared(db) HistoryResponse
        +GET_history_id(conversation_id, db) HistoryResponse
        +DELETE_history_id(conversation_id, db)
    }

    class SettingsRouter {
        +GET_settings_model(db) dict
        +PUT_settings_model(body, db) dict
        +GET_models() dict
    }

    %% ── API Service — Models ─────────────────────────────────────────────────

    class ChatRequest {
        +UUID conversation_id
        +str interface
        +str message
    }

    class ChatResponse {
        +UUID conversation_id
        +UUID message_id
        +str response
    }

    class MessageOut {
        +UUID id
        +str role
        +str content
        +datetime created_at
    }

    class HistoryResponse {
        +UUID conversation_id
        +str interface
        +list~MessageOut~ messages
    }

    %% ── API Service — Services ───────────────────────────────────────────────

    class ConnectionManager {
        -list~WebSocket~ _connections
        +connect(websocket)
        +disconnect(websocket)
        +broadcast(payload)
    }

    class ConversationService {
        +get_or_create_shared_conversation(db) str
        +fetch_history(db, conversation_id) list~dict~
        +store_message(db, conversation_id, role, content) str
    }

    class OpenRouterService {
        +str OPENROUTER_API_URL
        +str MODEL
        +str BASE_SYSTEM_PROMPT
        +str VOICE_BREVITY_PROMPT
        +get_openrouter_response(history, model, skill_context, interface) str
    }

    class SkillRouter {
        -_TRIGGER_MAP dict
        +route(message) list~str~
        -_should_fetch_news(message) bool
        -_should_fetch_cve(message) bool
        -_should_fetch_virustotal(message) bool
    }

    class Database {
        +str DATABASE_URL
        +AsyncEngine engine
        +get_db() AsyncSession
        +ping_db() bool
    }

    %% ── Skills ───────────────────────────────────────────────────────────────

    class VirusTotalSkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str _BASE_URL
        -str _API_KEY
        -_extract_target(message) tuple
        -_verdict(stats) str
        -_top_labels(results) list~str~
        +fetch(message) dict
        +format(data) str
    }

    class CVESkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str NVD_BASE_URL
        +int _CVE_LIMIT
        +int _DAYS_BACK
        -_parse_cve(cve) dict
        +fetch() list~dict~
        +format(cves) str
    }

    class TechNewsSkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str HN_BASE_URL
        +int _STORY_LIMIT
        +fetch() list~dict~
        +format(stories) str
    }

    %% ── External APIs ────────────────────────────────────────────────────────

    class VirusTotalAPI {
        <<external>>
        +GET /api/v3/files/hash
        +GET /api/v3/urls/base64url
        Requires: x-apikey header
        Free tier: 500 req/day
    }

    class NVDAPI {
        <<external>>
        +GET /rest/json/cves/2.0
        Params: pubStartDate, pubEndDate
        Optional: apiKey header
        Free tier: 5 req/30s (unkeyed)
        +Rate limit: 50 req/30s (keyed)
    }

    class HackerNewsAPI {
        <<external>>
        +GET /v0/topstories.json
        +GET /v0/item/id.json
        No auth required
    }

    class OpenRouterAPI {
        <<external>>
        +POST /api/v1/chat/completions
        Requires: Authorization Bearer
        Returns: LLM completion
    }

    class EdgeTTSAPI {
        <<external>>
        +WebSocket synthesis stream
        No auth required
        Returns: MP3 audio stream
    }

%    class OWWModels {
%        <<external>>
%        +melspectrogram.onnx
%        +embedding_model.onnx
%        Downloaded once on first run
%    }

    %% ── Relationships ────────────────────────────────────────────────────────

    VoiceMain --> WakeWordModule : calls run_forever
    VoiceMain --> STTModule : calls transcribe
    VoiceMain --> TTSModule : calls speak
    VoiceMain --> VoiceAPIClient : calls send_message
    VoiceMain --> AudioModule : calls record_until_silence
    WakeWordModule --> MicrophoneStream : opens stream
    % WakeWordModule --> OWWModels : downloads on first run
    AudioModule --> MicrophoneStream : opens stream

    ChatRouter --> ConversationService : resolve + store messages
    ChatRouter --> SkillRouter : route(message)
    ChatRouter --> OpenRouterService : get_openrouter_response
    ChatRouter --> ConnectionManager : broadcast turn
    ChatRouter --> Database : get_db dependency
    HistoryRouter --> ConversationService : fetch_history
    HistoryRouter --> Database : get_db dependency

    SkillRouter --> VirusTotalSkill : activates
    SkillRouter --> CVESkill : activates
    SkillRouter --> TechNewsSkill : activates

    VirusTotalSkill --> VirusTotalAPI : HTTPS GET (hash or URL lookup)
    CVESkill --> NVDAPI : HTTPS GET (date range query)
    TechNewsSkill --> HackerNewsAPI : HTTPS GET (top stories)
    OpenRouterService --> OpenRouterAPI : HTTPS POST (chat completion)
    TTSModule --> EdgeTTSAPI : WebSocket (text → MP3)

    HistoryResponse "1" *-- "many" MessageOut : contains
    VoiceAPIClient ..> ChatRequest : sends
    VoiceAPIClient ..> ChatResponse : receives
```

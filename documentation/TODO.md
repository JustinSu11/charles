# Charles — Actionable Tasks

> ✅ **Architecture approved 2026-02-16.** Voice-first dual interface is active. See `documentation/DesignDoc.md` on `develop` branch for full task breakdown.

## Phase 0 — Project Setup & Infrastructure (Mostly Done)

- [x] Initialize git repository with branch strategy (`main`, `develop`, `feature/*`)
- [x] Create `.env.example` with required keys
- [x] Write `docker-compose.yml` (Open WebUI running)
- [x] Configure persistent Docker volume (`open-webui-data`)
- [x] Set up `.gitignore`
- [x] Create monorepo folder structure (`/launcher`, `/voice`, `/api`, `/mcp`, `/docs`)
- [x] Create `requirements.txt` for voice service Python dependencies

## Phase 1 — Docker Backend (Next Up)

### PostgreSQL

- [x] Design database schema: `conversations` table (id, interface, timestamp) and `messages` table (id, conversation_id, role, content, timestamp)
- [x] Write initialization SQL script that runs on first container start
- [x] Add PostgreSQL service to `docker-compose.yml` with named volume
- [x] Verify data persists across `docker-compose down` / `up` cycles

### Charles API Service

- [x] Set up FastAPI project in `/api` with health check endpoint (`GET /health`)
- [x] Implement OpenRouter client (`qwen/qwen3-next-80b-a3b-instruct:free`) with API key from env
- [x] Implement `POST /chat` endpoint (message + conversation ID → OpenRouter → store in PostgreSQL → return response)
- [x] Implement `GET /history/{conversation_id}` endpoint
- [x] Implement `DELETE /history/{conversation_id}` endpoint
- [x] Add CORS config (allow Open WebUI on localhost:3000 and voice service)
- [x] Add error handling for OpenRouter failures (rate limits, timeouts)
- [x] Write Dockerfile for the API service (`python:3.11-slim`)
- [x] Add Charles API service to `docker-compose.yml`

### Open WebUI

- [x] Configure Open WebUI container to point to Charles API as its backend
- [ ] Verify chat history is shared between voice and web interfaces
- [ ] Confirm web interface is accessible at `localhost:3000` after `docker-compose up`

## Phase 2 — MCP Server Integration

- [ ] Implement MCP protocol client in Charles API (connect, discover, call tools)
- [ ] Integrate MCP tool-calling into OpenRouter request flow
- [ ] Add error handling for MCP server failures (graceful degradation)
- [ ] **VirusTotal MCP Server**: scan URL, look up file hash, check credential leaks; rate limit handling (4 req/min)
- [ ] **Vulnerability DB MCP Server**: evaluate source (NVD, CVE Details, OSV, Vulners), search by keyword, lookup CVE ID, filter by severity
- [ ] **Tech News MCP Server**: fetch headlines, search by keyword, filter by date range

## Phase 3 — Voice Service

- [ ] Generate custom "Hey Charles" wake word model (`.ppn`) via Picovoice Console
- [ ] Integrate `pvporcupine` with always-on microphone loop
- [ ] Integrate `openai-whisper` — benchmark base/small/medium, auto-download on first run
- [ ] Implement audio capture buffer + silence detection
- [ ] Integrate `piper-tts` — select English voice, implement TTS playback pipeline
- [ ] Implement speech interruption (wake word during playback stops and listens)
- [ ] Implement HTTP client to send transcribed text to `POST /chat`
- [ ] Test full audio pipeline on Windows (WASAPI), macOS (CoreAudio), Linux (ALSA)
- [ ] Implement audio device enumeration for users with multiple mics/speakers

## Phase 4 — GUI Launcher

- [ ] Build Tkinter launcher window: Start/Stop, status indicator, Open Web Interface button
- [ ] Implement process management (start/stop Docker Compose + voice service)
- [ ] Build first-time setup wizard (detect missing `.env`, guide through OpenRouter key, save to `.env`)
- [ ] Build settings dialog for updating API keys
- [ ] Add startup validation (check Docker is running before starting)
- [ ] Display real-time status from voice service (Listening / Transcribing / Speaking / Error)
- [ ] Handle graceful shutdown with confirmation dialog
- [ ] Package with PyInstaller for Windows, macOS, Linux
- [ ] Test packaged executable on a clean machine for each platform

## Phase 5 — Testing

- [ ] Wake word accuracy (false positive/negative rates across speakers and noise)
- [ ] STT accuracy (Whisper across accents, speeds, noise)
- [ ] MCP integration tests for all 3 servers
- [ ] End-to-end voice flow test
- [ ] Shared history test (voice → web handoff)
- [ ] Cross-platform test suite (Windows, macOS, Linux)
- [ ] First-time setup test on clean machine
- [ ] Graceful degradation test (voice fails → web-only fallback)

## Phase 6 — Documentation & Packaging

- [ ] `README.md`: quick start in under 5 steps
- [ ] `USER_GUIDE.md`: example voice commands, voice vs web switching
- [ ] `DEVELOPER.md`: architecture, how to add a new MCP server
- [ ] `TROUBLESHOOTING.md`: audio issues per platform, Docker errors, API key errors
- [ ] API documentation for all Charles API endpoints
- [ ] Distributable ZIP package (executable + `.env.template` + README)
- [ ] Test install from ZIP on clean Windows, macOS, Linux

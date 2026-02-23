# Charles - AI Assistant

> ✅ **APPROVED (2026-02-16)**: Voice-first dual interface architecture approved. Implementation is active. Web-only fallback plan no longer needed.

## Intent

Charles is a **hands-free voice AI assistant** with dual interfaces, designed to provide accessible AI capabilities for users both at their desk and away from their computer. The project enables users to interact with AI while doing other tasks (folding clothes, cooking, etc.) through natural voice commands, while also providing a traditional web interface for visual tasks.

**Primary Use Case:**
"Hey Charles, check if there's any React vulnerability news, then scan my GitHub repos to see if any of my projects are exposed" - *all while folding laundry*

**Dual Purpose:**
1. **Deliver**: Self-hosted voice + web AI assistant with MCP integration
2. **Learn**: Docker, voice processing (STT/TTS), MCP protocol, GUI development, cross-platform deployment

## Goals

### Project Goals
1. **Hands-Free Voice Interaction**: Primary interface via wake word + voice commands
2. **Dual Interface**: Voice for hands-free + Web UI for visual tasks
3. **One-Click Launch**: Non-technical users can start Charles with a single click
4. **Self-Hosted**: Full control over deployment and data privacy
5. **Cross-Platform**: Run seamlessly on Windows, Linux, and macOS
6. **MCP Integration**: Connect 3 MCP servers (VirusTotal, CVE Details, Tech News)

### Learning Objectives
1. **Voice Processing**: Speech-to-text (Whisper), Text-to-speech (Piper), Wake word detection
2. **Docker Fundamentals**: Multi-container orchestration, volume management
3. **MCP Protocol**: Model Context Protocol server integration
4. **GUI Development**: Python Tkinter desktop application
5. **Cross-Platform Development**: Handle platform-specific audio quirks
6. **User Experience**: Design for non-technical users

## Scope

### In Scope
- **Voice Interface**: Wake word detection, STT, TTS, always-listening mode
- **Web Interface**: Open WebUI for visual chat, code display, links
- **GUI Launcher**: One-click desktop app to start/stop Charles
- **Docker Backend**: PostgreSQL, API service, Open WebUI containers
- **Native Voice Service**: Runs on host machine for audio device access
- **MCP Servers**: VirusTotal, CVE Details, Tech News aggregation
- **Shared Context**: Both interfaces share conversation history
- **First-Time Setup**: GUI wizard for API key configuration
- **Cross-platform audio**: Handle Windows, Mac, Linux audio differences

### Out of Scope
- Cloud deployment (self-hosted only)
- Mobile app development
- Custom training/fine-tuning models
- Multi-user enterprise features (single-user focus)
- Production-grade scaling
- App store distribution (direct download only for PoC)

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────┐
│                   CHARLES LAUNCHER                       │
│                   (GUI Desktop App)                      │
│  [Start Charles] [Open Web UI] [Settings]               │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌──────────────────────────┐
│  VOICE INTERFACE │    │  WEB INTERFACE           │
│  (Native Python) │    │  (Docker Container)      │
├──────────────────┤    ├──────────────────────────┤
│ • Wake Word      │    │ • Open WebUI             │
│ • Whisper (STT)  │    │ • localhost:3000         │
│ • Piper (TTS)    │    │ • Visual chat            │
│ • Microphone     │    │ • Code display           │
│ • Speakers       │    │ • Clickable links        │
└────────┬─────────┘    └────────┬─────────────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌────────────────────────┐
         │   CHARLES CORE API     │
         │   (Docker Container)   │
         ├────────────────────────┤
         │ • OpenRouter Client    │
         │ • MCP Orchestration    │
         │ • Conversation Logic   │
         └────────┬───────────────┘
                  │
         ┌────────┴────────────────────────┐
         │                                 │
         ▼                                 ▼
┌─────────────────┐            ┌───────────────────┐
│   POSTGRESQL    │            │   MCP SERVERS     │
│  (Shared State) │            ├───────────────────┤
├─────────────────┤            │ • VirusTotal API  │
│ • User profile  │            │ • CVE Details API │
│ • Conversations │            │ • Tech News API   │
│ • Preferences   │            └───────────────────┘
└─────────────────┘
```

### Component Breakdown

**1. GUI Launcher (charles-launcher.py)**
- Desktop app with start/stop controls
- First-time setup wizard (API key input)
- Status indicators (listening, processing, stopped)
- Quick access to web UI
- Settings management

**2. Voice Service (Native Python App)**
- Runs on host machine (audio device access)
- Porcupine wake word detection ("Hey Charles")
- Whisper STT (local, offline)
- Piper TTS (local, offline)
- Communicates with Docker backend via HTTP

**3. Docker Backend**
- PostgreSQL: Shared conversation history
- Charles API: OpenRouter + MCP orchestration
- Open WebUI: Web interface

**4. MCP Servers (External APIs)**
- VirusTotal: Check API keys, file hashes
- CVE Details: Search vulnerabilities
- Tech News: Aggregate tech/security news

## Technology Stack

### Launcher & Voice (Native - Runs on Host)
- **Python 3.10+**: Core runtime
- **Tkinter**: GUI framework (cross-platform, built-in)
- **Porcupine (Picovoice)**: Wake word detection
- **OpenAI Whisper**: Speech-to-text (local, offline)
- **Piper TTS**: Text-to-speech (local, offline)
- **PyAudio**: Microphone/speaker access
- **Requests**: HTTP client for backend API

### Backend (Docker Containers)
- **PostgreSQL 16**: Database for shared state
- **FastAPI** or **Flask**: Charles API service
- **Open WebUI**: Web interface (ghcr.io/open-webui/open-webui:main)
- **Docker Compose**: Multi-container orchestration

### AI & APIs
- **OpenRouter API**: Cloud LLM inference (meta-llama/llama-3.3-70b-instruct:free)
- **MCP Protocol**: Model Context Protocol for tool integration
- **VirusTotal API**: Security scanning
- **CVE Details API**: Vulnerability data
- **Tech News APIs**: News aggregation (NewsAPI, etc.)

### Infrastructure
- Port 3000: Open WebUI
- Port 8000: Charles API
- Port 5432: PostgreSQL
- Local audio devices: Microphone + speakers

## System Requirements

### Hardware

**Minimum:**
- **CPU**: Dual-core processor (2+ GHz)
- **RAM**: 6GB (4GB backend + 2GB voice service)
- **Storage**: 3GB free (Docker images + Whisper model)
- **GPU**: Not required
- **Microphone**: Any USB or built-in mic
- **Speakers**: Any audio output device
- **Network**: Internet connection for OpenRouter API

**Recommended:**
- **CPU**: Quad-core processor
- **RAM**: 8GB
- **Storage**: 5GB free
- **Microphone**: Good quality for better voice recognition
- **Network**: Broadband internet

### Software

**Required:**
- **Docker Desktop**: Latest stable version
- **Python 3.10+**: For voice service and launcher
- **Operating System**: Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)

**Auto-Installed:**
- Python packages (via pip install -r requirements.txt)
- Docker images (auto-pulled on first run)
- Whisper models (auto-downloaded on first run)
- Piper voices (auto-downloaded on first run)

### Why These Requirements?

**Voice Processing Local:**
- Privacy: Voice data never leaves your machine
- Speed: No API latency for STT/TTS
- Offline: Works without internet (except for AI responses)
- Cost: No per-minute charges for transcription

**Backend in Docker:**
- Consistency: Same environment across platforms
- Isolation: Clean, reproducible setup
- Easy updates: Pull new images

**Trade-offs:**
- ✅ Complete privacy (voice data local)
- ✅ Fast voice processing
- ⚠️ Slightly higher RAM usage (6GB vs 4GB web-only)
- ⚠️ Internet required for AI responses (OpenRouter)

## Deliverables

### 1. GUI Launcher ⏳ (Approved)
- **charles-launcher.py**: Desktop application
- Start/stop button with status indicator
- First-time setup wizard (API key input)
- Settings dialog (API key management)
- Quick access to web interface
- Cross-platform executable (PyInstaller)

### 2. Voice Service ⏳ (Approved)
- **charles-voice/**: Native Python application
- Wake word detection ("Hey Charles")
- Speech-to-text (Whisper local)
- Text-to-speech (Piper local)
- API client for backend communication
- Audio pipeline (microphone → STT → backend → TTS → speakers)
- Cross-platform audio handling

### 3. Docker Backend 🚧 (Updated)
- **PostgreSQL**: Shared database
- **Charles API**: OpenRouter + MCP orchestration
- **Open WebUI**: Web interface
- **docker-compose.yml**: Multi-container setup

### 4. MCP Server Integration 🚧 (In Progress)
- VirusTotal MCP server
- CVE Details MCP server
- Tech News MCP server
- MCP protocol client library

### 5. Documentation ⏳
- **README.md**: Quick start guide
- **USER_GUIDE.md**: Voice commands, features
- **DEVELOPER.md**: Architecture, contributing
- **TROUBLESHOOTING.md**: Common issues

### 6. Packaging 🚧
- PyInstaller build scripts
- Distributable ZIP package
- Platform-specific installers (optional v2.0)

## User Experience Flow

### First Time Setup

```
1. User downloads charles-v1.0.zip
2. Extracts to folder
3. Double-clicks Charles.exe (or Charles.app on Mac)
   ↓
4. "Welcome to Charles!" dialog appears
   ↓
5. Browser opens to openrouter.ai/keys
   ↓
6. User signs up, copies API key
   ↓
7. Pastes API key into wizard
   ↓
8. "Setup Complete!" message
   ↓
9. Launcher window appears
10. User clicks "Start Charles" button
    ↓
11. Status changes to "● Listening" (green)
12. User says "Hey Charles, what can you do?"
    ↓
13. Charles responds via speakers
```

### Daily Use

```
Option A: Voice (hands-free)
1. User: "Hey Charles"
2. Charles: "Yes?" (acknowledges)
3. User: "Check tech news for React vulnerabilities"
4. Charles: "I found 2 recent React vulnerabilities..."

Option B: Web UI (visual)
1. User clicks "Open Web Interface" button
2. Browser opens to localhost:3000
3. Types: "Show me code examples for those React vulns"
4. Charles displays formatted code with syntax highlighting
```

### Stopping Charles

```
1. User clicks "Stop Charles" in launcher
   OR
2. User closes launcher window
   ↓
3. Confirmation: "Stop Charles and quit?"
   ↓
4. Services stop gracefully
5. Application exits
```

## Quality Standards

### Testing Requirements
- ⏳ Voice recognition accuracy testing (different accents, noise levels)
- ⏳ Wake word false positive/negative rates
- ⏳ Cross-platform audio pipeline validation
- ⏳ MCP server integration tests
- ⏳ End-to-end workflow tests (voice → response → TTS)
- ⏳ GUI launcher tests on Windows, Mac, Linux
- ⏳ First-time setup wizard testing

### Code Standards
- Clear commit messages (conventional commits)
- Feature branch workflow (main, develop, feature/*)
- Code review before merging
- Type hints in Python code
- Docstrings for public functions
- Error handling for audio failures

### Documentation
- README with quick start (< 5 steps)
- Voice command examples
- Troubleshooting guide for audio issues
- Architecture diagrams
- API documentation for backend

### User Experience
- Non-technical users can install and run
- Setup process < 5 minutes
- Clear error messages
- Graceful degradation (web-only if voice fails)
- Status feedback (visual + audio)

## Dependencies

### External Dependencies
- **Docker Desktop**: Backend containers
- **OpenRouter API**: LLM inference (requires API key)
- **MCP Servers**: External APIs (VirusTotal, CVE, News)
- **Python 3.10+**: Voice service runtime
- **Audio drivers**: Platform-specific (ALSA/PulseAudio on Linux, CoreAudio on Mac, WASAPI on Windows)

### Python Dependencies (Voice Service)
```
openai-whisper==20231117
piper-tts==1.2.0
pvporcupine==3.0.0
pyaudio==0.2.14
requests==2.31.0
python-dotenv==1.0.0
```

### Docker Images
```
postgres:16
ghcr.io/open-webui/open-webui:main
python:3.11-slim (for Charles API)
```

### Internal Dependencies
- Voice service depends on backend API
- Web UI depends on backend API
- Backend API depends on PostgreSQL
- All depend on OpenRouter API availability

## Stakeholders

- **Justin** - Primary developer
- **Client/Team** - Requested hands-free voice interaction (pending approval)
- **End Users** - Non-technical users wanting voice AI assistant

## Success Criteria

### MVP (Minimum Viable Product)
- ⏳ GUI launcher starts with one click
- ⏳ Voice wake word detection works ("Hey Charles")
- ⏳ Speech-to-text accurately transcribes commands
- ⏳ OpenRouter integration responds to queries
- ⏳ MCP servers execute tools (VirusTotal, CVE, News)
- ⏳ Text-to-speech speaks responses naturally
- ⏳ Web UI accessible at localhost:3000
- ⏳ Both interfaces share conversation history
- ⏳ Data persists across restarts

### Full Release v1.0
- ⏳ Cross-platform support (Windows, Mac, Linux)
- ⏳ Packaged executable (no manual Python install)
- ⏳ Complete documentation
- ⏳ Testing passed on all platforms
- ⏳ Known issues documented
- ⏳ User guide with voice command examples

### Future Enhancements (v2.0)
- System tray integration (minimize to tray)
- Auto-start on boot (optional setting)
- Custom wake word training
- Multi-language support
- Voice settings (speed, pitch, volume)
- Conversation export/import
- Plugin system for additional MCP servers

## Risk Register

### Current Risks

**1. Team Approval Pending** - HIGH
- **Risk**: Client/team may not approve voice-first architecture
- **Impact**: Major rework required, delays timeline
- **Mitigation**: Document current state, be ready to revert to web-only
- **Status**: PENDING (awaiting approval 2026-02-14)

**2. Cross-Platform Audio Complexity** - MEDIUM
- **Risk**: Audio device access may fail on some platforms
- **Impact**: Voice features don't work for some users
- **Mitigation**:
  - Test on all platforms early
  - Provide fallback to web-only mode
  - Document platform-specific audio setup
- **Status**: Monitoring (not implemented yet)

**3. Wake Word False Positives** - MEDIUM
- **Risk**: Wake word triggers unintentionally
- **Impact**: Unexpected responses, user frustration
- **Mitigation**:
  - Use proven wake word engine (Porcupine)
  - Allow sensitivity adjustment in settings
  - Visual feedback when wake word detected
- **Status**: Monitoring (not implemented yet)

**4. Voice Recognition Accuracy** - MEDIUM
- **Risk**: Whisper may not accurately transcribe all accents/environments
- **Impact**: Commands misunderstood, poor UX
- **Mitigation**:
  - Use latest Whisper model (proven accuracy)
  - Allow manual correction via web UI
  - Provide voice command examples
- **Status**: Monitoring (not implemented yet)

**5. Non-Technical User Setup** - LOW
- **Risk**: Users struggle with first-time setup (API key, Docker)
- **Impact**: Adoption barrier, support burden
- **Mitigation**:
  - GUI setup wizard with clear instructions
  - Auto-open browser to OpenRouter signup
  - Video walkthrough tutorial
- **Status**: Monitoring (GUI wizard designed)

**6. MCP Server Integration** - MEDIUM (carried over)
- **Risk**: MCP protocol may be complex to integrate
- **Impact**: Core features delayed
- **Mitigation**: Start with simple MCP examples, iterate
- **Status**: In progress

## Current Status

**Phase**: Active Development
**Health**: On Track
**Last Updated**: 2026-02-18

### Recent Activity
- **2026-02-13**: Major architecture redesign
  - Identified hands-free voice as primary use case
  - Designed dual interface (voice + web)
  - Designed GUI launcher for one-click setup
  - Updated tech stack (Whisper, Piper, Porcupine)
  - Documented cross-platform voice architecture
  - Pending team/client approval before implementation

- **2026-02-11**: Initial setup
  - Project initialization (2 commits on main)
  - Created feature branch for MCP server connection
  - Docker Compose configuration working
  - Cross-platform startup scripts functional

### Active Work
- **Status**: ACTIVE - Architecture approved 2026-02-16
- **Focus**: Dual interface (voice + web) with GUI launcher
- **Blockers**: None

### Decision Points (2026-02-14) — Resolved 2026-02-16
1. ✅ **Approved** — Voice-first dual interface approach
2. ✅ **Approved** — One-click GUI launcher (vs command-line)
3. ✅ **Approved** — 6GB RAM requirement (vs 4GB web-only)
4. Proceed with PoC scope (3 MCP servers)?

### Next Steps (If Approved)
1. Build GUI launcher prototype (charles-launcher.py)
2. Implement wake word detection (Porcupine)
3. Integrate Whisper STT (local)
4. Integrate Piper TTS (local)
5. Build Charles API backend (FastAPI)
6. Connect MCP servers (VirusTotal, CVE, News)
7. Test end-to-end voice flow
8. Package as executable (PyInstaller)
9. Test on Windows, Mac, Linux
10. Document voice commands and setup

### Next Steps (If Not Approved - Fallback Plan)
1. Continue with web-only Open WebUI approach
2. Focus on MCP server integration
3. Complete 3 MCP servers (VirusTotal, CVE, News)
4. Test web interface thoroughly
5. Document web-based usage
6. Release v1.0 (web-only)

## Developer Task Breakdown

### Phase 0 — Project Setup & Infrastructure

- [ ] Initialize git repository with branch strategy (`main`, `develop`, `feature/*`)
- [ ] Create monorepo folder structure (`/launcher`, `/voice`, `/api`, `/mcp`, `/docs`)
- [ ] Create `.env.template` with all required keys (OpenRouter, VirusTotal, vulnerability DB, news API)
- [ ] Write `docker-compose.yml` defining PostgreSQL, Charles API, and Open WebUI services with shared network
- [ ] Configure persistent Docker volumes for PostgreSQL data and conversation history
- [ ] Create `requirements.txt` for voice service Python dependencies
- [ ] Set up `.gitignore` (exclude `.env`, Whisper model files, Piper voice files, `__pycache__`)

---

### Phase 1 — Docker Backend

#### PostgreSQL
- [ ] Design database schema: `conversations` table (id, interface, timestamp) and `messages` table (id, conversation_id, role, content, timestamp)
- [ ] Write initialization SQL script that runs on first container start
- [ ] Verify data persists across `docker-compose down` / `up` cycles using the named volume

#### Charles API Service
- [ ] Set up FastAPI (or Flask) project inside `/api` with a health check endpoint (`GET /health`)
- [ ] Implement OpenRouter client with model configuration (`meta-llama/llama-3.3-70b-instruct:free`) and API key loaded from environment
- [ ] Implement `POST /chat` endpoint that accepts a message and conversation ID, calls OpenRouter, stores the exchange in PostgreSQL, and returns the response
- [ ] Implement `GET /history/{conversation_id}` endpoint to retrieve message history
- [ ] Implement `DELETE /history/{conversation_id}` endpoint to clear history
- [ ] Add CORS configuration to allow requests from Open WebUI (localhost:3000) and the voice service
- [ ] Add error handling for OpenRouter failures (rate limits, timeouts, bad responses)
- [ ] Write Dockerfile for the API service using `python:3.11-slim`

#### Open WebUI
- [ ] Configure Open WebUI container to point to Charles API as its backend
- [ ] Verify chat history is shared between voice and web interfaces (same conversation ID scheme)
- [ ] Confirm web interface is accessible at `localhost:3000` after `docker-compose up`

---

### Phase 2 — MCP Server Integration

#### MCP Client (Charles API)
- [ ] Implement MCP protocol client in the Charles API that can connect to, discover, and call tools on MCP servers
- [ ] Integrate MCP tool-calling into the OpenRouter request flow (function/tool calling)
- [ ] Add error handling for MCP server failures so the assistant degrades gracefully without crashing

#### VirusTotal MCP Server
- [ ] Create MCP server with the following tools:
  - Scan a URL for threats
  - Look up a file hash
  - Check whether an API key or credential string appears in known leaks
- [ ] Load VirusTotal API key from environment
- [ ] Add rate limit handling (VirusTotal free tier: 4 requests/min)
- [ ] Register server with Charles API and verify end-to-end tool call works

#### Vulnerability Database MCP Server
> ⚠️ **Note**: Final vulnerability data source TBD — evaluate available options before building. Design the MCP server interface so the underlying data source can be swapped without changing how Charles API calls it.

- [ ] Evaluate and select vulnerability database source (consider: NVD, CVE Details, OSV, Vulners, or others)
- [ ] Create MCP server with the following tools:
  - Search vulnerabilities by keyword or technology name
  - Look up a specific CVE ID and return severity, description, and affected versions
  - Filter by severity level (Critical / High / Medium / Low)
- [ ] Handle pagination for large result sets
- [ ] Register server with Charles API and verify end-to-end tool call works

#### Tech News MCP Server
- [ ] Select news aggregation source (NewsAPI, Hacker News API, or RSS feeds)
- [ ] Create MCP server with the following tools:
  - Fetch recent tech/security headlines
  - Search news by keyword or topic
  - Filter by date range
- [ ] Load API key from environment (if required by chosen source)
- [ ] Register server with Charles API and verify end-to-end tool call works

---

### Phase 3 — Voice Service

#### Wake Word Detection
- [ ] Generate custom "Hey Charles" wake word model (`.ppn` file) via Picovoice Console
- [ ] Integrate `pvporcupine` into the voice service with the custom model file
- [ ] Implement the always-on microphone loop that listens for the wake word
- [ ] Add configurable sensitivity setting (stored in `.env` or config file)
- [ ] Provide visual feedback in the launcher when wake word fires (status indicator changes)
- [ ] Handle microphone access errors gracefully with a clear error message to the user

#### Speech-to-Text (Whisper)
- [ ] Integrate `openai-whisper` into the voice service
- [ ] Benchmark `base`, `small`, and `medium` model sizes for accuracy vs. latency — document results and select one
- [ ] Auto-download the selected Whisper model on first run if not present
- [ ] Implement audio capture buffer: record audio after wake word until silence is detected
- [ ] Implement silence detection to determine when the user has finished speaking
- [ ] Add timeout handling if no speech is detected after wake word (re-enter listening state)
- [ ] Add transcription error handling (empty result, low confidence)

#### Text-to-Speech (Piper)
- [ ] Integrate `piper-tts` into the voice service
- [ ] Select default English voice model and auto-download on first run
- [ ] Implement TTS playback pipeline: receive text from API → synthesize → play through speakers
- [ ] Implement speech interruption: if wake word fires while Charles is speaking, stop playback and listen
- [ ] Add audio output device selection/fallback

#### Voice Service API Client
- [ ] Implement HTTP client in the voice service that sends transcribed text to `POST /chat` on the Charles API
- [ ] Use a consistent `voice` conversation ID so voice history is tracked separately from web history
- [ ] Handle API errors (service not running, timeout, bad response) and speak a fallback error message to the user

#### Cross-Platform Audio
- [ ] Test full audio pipeline (mic input → STT → TTS → speaker output) on Windows (WASAPI)
- [ ] Test full audio pipeline on macOS (CoreAudio)
- [ ] Test full audio pipeline on Linux (ALSA/PulseAudio)
- [ ] Document any platform-specific setup steps discovered during testing
- [ ] Implement audio device enumeration so users with multiple mics/speakers can select the right one

---

### Phase 4 — GUI Launcher

- [ ] Build main launcher window with Tkinter: Start/Stop button, status indicator (Stopped / Listening / Processing / Speaking / Error), and Open Web Interface button
- [ ] Implement process management: Start button starts Docker Compose services and the voice service; Stop button shuts both down gracefully
- [ ] Build first-time setup wizard: detect missing `.env` / API key on launch, guide user through getting an OpenRouter key (auto-open browser), save key to `.env`
- [ ] Build settings dialog: allow user to view and update API keys without re-running the wizard
- [ ] Add startup validation: check Docker is running before attempting to start services, show clear error if not
- [ ] Display real-time status updates from the voice service (e.g., "Wake word detected", "Transcribing…", "Charles is speaking")
- [ ] Handle graceful shutdown: confirm dialog before closing, ensure Docker containers and voice service stop cleanly
- [ ] Package launcher as a standalone executable using PyInstaller for Windows, macOS, and Linux
- [ ] Test packaged executable on a clean machine (no Python pre-installed) for each platform

---

### Phase 5 — Testing

- [ ] **Wake word accuracy**: test false positive rate (similar words that shouldn't trigger) and false negative rate (saying "Hey Charles" that doesn't trigger) across different speakers and noise environments
- [ ] **STT accuracy**: test Whisper transcription across different accents, speaking speeds, and background noise levels — document results
- [ ] **MCP integration tests**: verify each MCP server tool returns correct results and Charles API correctly incorporates them into responses
- [ ] **End-to-end voice flow**: full test from "Hey Charles" → STT → API → MCP tool call → response → TTS → speaker
- [ ] **Shared history test**: verify a conversation started via voice continues correctly when switched to web UI and vice versa
- [ ] **Cross-platform tests**: run full test suite on Windows, macOS, and Linux
- [ ] **First-time setup test**: run setup wizard on a clean machine with no prior configuration
- [ ] **Graceful degradation test**: verify launcher shows useful error and falls back to web-only if voice service fails to start

---

### Phase 6 — Documentation & Packaging

- [ ] Write `README.md`: quick start in under 5 steps, prerequisites, and first-time setup
- [ ] Write `USER_GUIDE.md`: example voice commands, how to switch between voice and web, tips for best recognition
- [ ] Write `DEVELOPER.md`: architecture overview, how to add a new MCP server, how to run services individually for debugging
- [ ] Write `TROUBLESHOOTING.md`: common audio issues per platform, Docker not found, API key errors, wake word not triggering
- [ ] Write API documentation for all Charles API endpoints
- [ ] Create distributable ZIP package (executable + `.env.template` + README)
- [ ] Test install from ZIP on clean Windows, macOS, and Linux machines

---

## Notes

- **Architecture approved 2026-02-16** - Implementation is active
- Prioritize cross-platform compatibility in all voice work
- Test audio on real hardware early (not just dev machine)
- Document platform-specific audio quirks as discovered
- Consider graceful degradation (web-only if voice fails)
- User experience paramount - non-technical users must succeed
- Privacy: All voice data processed locally (never sent to cloud)
- Clear visual feedback for voice states (listening, processing, speaking)

## Open Questions

**Technical:**
- Which Whisper model size? (base vs small vs medium - tradeoff: accuracy vs speed)
- ~~Custom wake word or pre-trained?~~ **RESOLVED**: Use Porcupine console to generate a custom "Hey Charles" `.ppn` model. Runs fully locally, free for personal use.
- Audio buffer size for low latency?
- How to handle audio device selection (multiple mics/speakers)?

**User Experience:**
- Should launcher minimize to system tray or taskbar?
- Auto-start on boot (default yes or no)?
- Visual indicator when Charles is listening?
- How to handle voice errors (repeat? show in web UI?)

**Scope:**
- Add push-to-talk mode as alternative to wake word?
- Support custom wake word training?
- Multi-user profiles on same machine?

**Deployment:**
- Distribute as ZIP or proper installer?
- Code sign executables? (costs money)
- Auto-update mechanism for v2.0?

---

**README for Developers:**

This CLAUDE.md reflects a **major architecture pivot** from web-only to voice-first dual interface. The changes are pending client/team approval (2026-02-14).

**Current state:** Design complete, implementation not started
**Risk:** May need to revert to web-only if not approved
**Backup:** Previous web-only architecture documented in git history

If implementing this architecture, start with GUI launcher prototype to validate UX before building full voice pipeline.

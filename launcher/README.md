# launcher/

GUI desktop launcher for Charles.

## What goes here

- `charles-launcher.py` — Tkinter desktop app (Start/Stop button, status indicator, Open Web Interface shortcut)
- First-time setup wizard (detects missing `.env`, guides user through OpenRouter key entry)
- Settings dialog for updating API keys
- PyInstaller spec file for building distributable executables

## Responsibilities

- Start/stop Docker Compose services and the voice service process
- Show real-time status from the voice service (Listening / Transcribing / Speaking / Error)
- Validate that Docker is running before attempting to start services
- Graceful shutdown with confirmation dialog

## Build (future)

```bash
pyinstaller charles-launcher.spec
```

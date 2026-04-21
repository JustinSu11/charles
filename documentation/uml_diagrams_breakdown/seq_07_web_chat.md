# Sequence Diagram 7 of 7 — Web Chat (Text Interface)

Covers: the text chat path from the Electron UI directly to the API, bypassing the voice service entirely. Skill routing and OpenRouter calls are identical to the voice path.

```mermaid
sequenceDiagram
    actor User
    participant UI as Electron UI<br>(renderer/index.html)
    participant Chat as POST /chat<br>(chat.py)
    participant SR as SkillRouter<br>(skill_router.py)
    participant DB as SQLite DB
    participant OR as OpenRouter API<br>(external)
    participant WS as WebSocket Manager<br>(ws_manager.py)

    Note over UI: Voice service not required<br>Text chat works independently

    User ->> UI: types message, presses Enter or Send

    UI ->> UI: showThinking() — animated dots

    UI ->> Chat: HTTP POST /chat<br>{message, interface:"web", conversation_id?}

    Chat ->> DB: get or create shared conversation
    DB -->> Chat: conversation_id
    Chat ->> DB: fetch message history
    DB -->> Chat: history rows
    Chat ->> DB: INSERT user message
    Chat ->> DB: SELECT active_model from app_state

    Chat ->> SR: route(message)
    Note over SR: Same keyword routing as voice<br>VT / CVE / HN skills activate identically
    SR -->> Chat: list of activated skill names

    opt Skill(s) activated (8 s timeout each)
        Chat ->> Chat: run_skill(name, message)<br>fetch external API data
        Note over Chat: See seq_03 / seq_04 / seq_05<br>for per-skill detail
        Chat -->> Chat: skill_context string
    end

    Chat ->> OR: HTTPS POST /api/v1/chat/completions<br>{history, system_prompt + skill_context, model}
    Note over OR: No voice brevity prompt<br>Full-length response for web interface
    OR -->> Chat: assistant reply text

    Chat ->> DB: INSERT assistant message
    Chat ->> WS: broadcast {type:"turn", interface:"web",<br>user:{content}, assistant:{content}}

    WS -->> UI: WebSocket push
    UI ->> UI: clearThinking()<br>renderTurn() — appends user + assistant bubbles
    UI -->> User: reply displayed in chat
```

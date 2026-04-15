# Sequence Diagram 3 of 7 — Skill: VirusTotal

Covers: how the VirusTotal skill is triggered, what API call is made, and how the result is injected into the LLM context. Triggered when the user's message contains a file hash, URL, "virustotal", "malware", or "is this safe".

```mermaid
sequenceDiagram
    participant Chat as POST /chat<br>(chat.py)
    participant SR as SkillRouter<br>(skill_router.py)
    participant VT as VirusTotal Skill<br>(virustotal.py)
    participant VTAPI as VirusTotal API v3<br>(virustotal.com)
    participant OR as OpenRouter API<br>(external)

    Chat ->> SR: route(message)
    Note over SR: Tier 1: "virustotal" / "virus total" / "vt scan"<br>Tier 2: MD5/SHA-1/SHA-256 hex string detected<br>Tier 3: "malware" / "is this safe"
    SR -->> Chat: ["virustotal"]

    Chat ->> VT: run_skill("virustotal", message)
    VT ->> VT: _extract_target(message)
    Note over VT: Regex: 32-char MD5<br>40-char SHA-1<br>64-char SHA-256<br>or https?:// URL

    alt Hash target
        VT ->> VTAPI: GET /api/v3/files/{hash}<br>Header: x-apikey
        VTAPI -->> VT: JSON {data.attributes}
    else URL target
        VT ->> VT: base64url-encode(url), strip padding
        VT ->> VTAPI: GET /api/v3/urls/{encoded}<br>Header: x-apikey
        VTAPI -->> VT: JSON {data.attributes}
    else No API key configured
        VT -->> Chat: None (no live data)
        Note over Chat: INSTRUCTIONS injected only<br>LLM constructs a direct VT link for user
    else Target not found (404)
        VTAPI -->> VT: 404 Not Found
        VT -->> Chat: {error: "not found in VT database"}
    end

    VT ->> VT: _verdict(last_analysis_stats)
    VT ->> VT: _top_labels(last_analysis_results)
    VT -->> Chat: skill_context block:<br>verdict, detection ratio,<br>malware labels, scanned_at, report URL

    Chat ->> OR: POST /chat/completions<br>{history, system_prompt + skill_context}
    OR -->> Chat: reply citing verdict and detection ratio
```

# Charles — Use Case Diagram

```mermaid
graph TB
    subgraph Actors
        U(["👤 User"])
        A(["🔧 Admin"])
    end

    subgraph Charles System

        subgraph Voice Interface
            UC1["Trigger wake word<br>(say 'Hey Jarvis' / custom)"]
            UC2["Speak a command<br>or question"]
            UC3["Interrupt Charles<br>mid-reply (barge-in)"]
            UC4["End conversation<br>(say 'goodbye' / 'stop')"]
        end

        subgraph Text Interface
            UC5["Type a message<br>in the chat UI"]
            UC6["View conversation<br>history"]
            UC7["Clear conversation<br>history"]
            UC8["Select AI model<br>from dropdown"]
        end

        subgraph Skills — Triggered Automatically by Message Content
            direction TB

            subgraph VT["VirusTotal Skill"]
                UC9["Check file hash<br>(MD5 / SHA-1 / SHA-256)"]
                UC10["Check URL<br>for malware"]
            end

            subgraph CVE["CVE Skill — NVD API"]
                UC11["Query recent CVEs<br>(last 7 days)"]
                UC12["Ask about a specific<br>vulnerability or exploit"]
                UC13["Get severity summary<br>(CVSS score + label)"]
            end

            subgraph HN["Tech News Skill"]
                UC14["Fetch top Hacker News<br>stories"]
                UC15["Ask about trending<br>tech topics"]
            end
        end

        subgraph Voice Service Controls
            UC16["Start voice service"]
            UC17["Stop voice service"]
            UC18["Interrupt current<br>TTS playback"]
        end

        subgraph Setup and Config
            UC19["Run first-time<br>setup wizard"]
            UC20["Add custom wake word<br>.onnx model file"]
            UC21["Configure .env<br>(API keys + thresholds)"]
            UC22["Re-run setup<br>via tray menu"]
        end

    end

    subgraph External APIs
        EXT1[["virustotal.com/api/v3<br>Requires: VIRUSTOTAL_API_KEY"]]
        EXT2[["services.nvd.nist.gov<br>Optional: NVD_API_KEY<br>(higher rate limit)"]]
        EXT3[["hacker-news.firebaseio.com<br>No auth required"]]
        EXT4[["openrouter.ai<br>Requires: OPENROUTER_API_KEY"]]
    end

    %% User → Voice
    U --> UC1
    U --> UC2
    U --> UC3
    U --> UC4

    %% User → Text
    U --> UC5
    U --> UC6
    U --> UC7
    U --> UC8

    %% Voice/Text → Skills (triggered automatically)
    UC2 -.->|hash / URL / 'virustotal'| UC9
    UC2 -.->|hash / URL / 'virustotal'| UC10
    UC2 -.->|'cve' / 'vulnerability'| UC11
    UC2 -.->|'cve' / 'zero-day'| UC12
    UC2 -.->|'cve' / 'vulnerability'| UC13
    UC2 -.->|'news' / 'trending'| UC14
    UC2 -.->|'news' / 'trending'| UC15
    UC5 -.->|hash / URL / 'virustotal'| UC9
    UC5 -.->|hash / URL / 'virustotal'| UC10
    UC5 -.->|'cve' / 'vulnerability'| UC11
    UC5 -.->|'cve' / 'zero-day'| UC12
    UC5 -.->|'news' / 'trending'| UC14

    %% Skills → External APIs
    UC9 -->|GET /api/v3/files/hash| EXT1
    UC10 -->|GET /api/v3/urls/encoded| EXT1
    UC11 -->|GET /rest/json/cves/2.0| EXT2
    UC12 -->|GET /rest/json/cves/2.0| EXT2
    UC13 -->|GET /rest/json/cves/2.0| EXT2
    UC14 -->|GET /v0/topstories.json| EXT3
    UC15 -->|GET /v0/topstories.json| EXT3
    UC2 -->|POST /api/v1/chat/completions| EXT4
    UC5 -->|POST /api/v1/chat/completions| EXT4

    %% User → Voice Controls
    U --> UC16
    U --> UC17
    U --> UC18

    %% Admin → Setup
    A --> UC19
    A --> UC20
    A --> UC21
    A --> UC22

    %% Includes
    UC1 -.->|includes| UC16
    UC2 -.->|extends| UC1

    style UC1  fill:#2e1065,color:#c4b5fd,stroke:#7c3aed
    style UC2  fill:#2e1065,color:#c4b5fd,stroke:#7c3aed
    style UC3  fill:#2e1065,color:#c4b5fd,stroke:#7c3aed
    style UC4  fill:#2e1065,color:#c4b5fd,stroke:#7c3aed
    style UC5  fill:#1e3a5f,color:#93c5fd,stroke:#2563eb
    style UC6  fill:#1e3a5f,color:#93c5fd,stroke:#2563eb
    style UC7  fill:#1e3a5f,color:#93c5fd,stroke:#2563eb
    style UC8  fill:#1e3a5f,color:#93c5fd,stroke:#2563eb
    style UC9  fill:#450a0a,color:#fca5a5,stroke:#991b1b
    style UC10 fill:#450a0a,color:#fca5a5,stroke:#991b1b
    style UC11 fill:#14532d,color:#86efac,stroke:#16a34a
    style UC12 fill:#14532d,color:#86efac,stroke:#16a34a
    style UC13 fill:#14532d,color:#86efac,stroke:#16a34a
    style UC14 fill:#78350f,color:#fcd34d,stroke:#b45309
    style UC15 fill:#78350f,color:#fcd34d,stroke:#b45309
    style UC16 fill:#431407,color:#fdba74,stroke:#c2410c
    style UC17 fill:#431407,color:#fdba74,stroke:#c2410c
    style UC18 fill:#431407,color:#fdba74,stroke:#c2410c
    style UC19 fill:#1f2937,color:#d1d5db,stroke:#4b5563
    style UC20 fill:#1f2937,color:#d1d5db,stroke:#4b5563
    style UC21 fill:#1f2937,color:#d1d5db,stroke:#4b5563
    style UC22 fill:#1f2937,color:#d1d5db,stroke:#4b5563
    style EXT1 fill:#1a0a0a,color:#f87171,stroke:#7f1d1d
    style EXT2 fill:#0a1a0a,color:#86efac,stroke:#14532d
    style EXT3 fill:#1a1200,color:#fcd34d,stroke:#78350f
    style EXT4 fill:#0a0a1a,color:#a5b4fc,stroke:#312e81
```

# Class Diagram 4 of 4 — Skills and External APIs

Detailed view of all three skill modules and the external APIs they depend on.

```mermaid
classDiagram
    direction TB

    class SkillRouter {
        -dict _TRIGGER_MAP
        +route(message str) list~str~
        -_should_fetch_virustotal(message str) bool
        -_should_fetch_cve(message str) bool
        -_should_fetch_news(message str) bool
    }

    class VirusTotalSkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str _BASE_URL
        -str _API_KEY
        -_extract_target(message str) tuple~str_str~
        -_verdict(stats dict) str
        -_top_labels(analysis_results dict, limit int) list~str~
        +fetch(message str) dict
        +format(data dict) str
    }

    class CVESkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str NVD_BASE_URL
        +int _CVE_LIMIT
        +int _DAYS_BACK
        -_parse_cve(cve dict) dict
        +fetch() list~dict~
        +format(cves list) str
    }

    class TechNewsSkill {
        +str DESCRIPTION
        +str INSTRUCTIONS
        +str HN_BASE_URL
        +int _STORY_LIMIT
        +fetch() list~dict~
        +format(stories list) str
    }

    class VirusTotalAPI {
        <<external>>
        Base URL: virustotal.com/api/v3
        Auth: x-apikey header
        Free tier: 500 req/day
        +GET /files/{hash}
        +GET /urls/{base64url_encoded}
        Returns: last_analysis_stats
        Returns: last_analysis_results
    }

    class NVDAPI {
        <<external>>
        Base URL: services.nvd.nist.gov
        +GET /rest/json/cves/2.0
        Params: pubStartDate, pubEndDate, resultsPerPage
        Auth: apiKey header (optional)
        Unkeyed rate limit: 5 req/30 s
        Keyed rate limit: 50 req/30 s
        Returns: vulnerabilities list
    }

    class HackerNewsAPI {
        <<external>>
        Base URL: hacker-news.firebaseio.com/v0
        No auth required
        +GET /topstories.json
        +GET /item/{id}.json
        Returns: ranked story IDs
        Returns: story objects
    }

    class OpenRouterAPI {
        <<external>>
        Base URL: openrouter.ai/api/v1
        Auth: Authorization Bearer token
        +POST /chat/completions
        Body: messages, model, system
        Returns: assistant reply content
    }

    class EdgeTTSAPI {
        <<external>>
        Protocol: WebSocket
        No auth required
        Input: text string + voice config
        Returns: MP3 audio stream
    }

    SkillRouter --> VirusTotalSkill : activates on hash/URL/malware keywords
    SkillRouter --> CVESkill : activates on CVE/vulnerability keywords
    SkillRouter --> TechNewsSkill : activates on news/trending keywords

    VirusTotalSkill --> VirusTotalAPI : HTTPS GET (hash or encoded URL)
    CVESkill --> NVDAPI : HTTPS GET (date range query)
    TechNewsSkill --> HackerNewsAPI : HTTPS GET (top stories + items)

    OpenRouterAPI ..> SkillRouter : skill_context injected into prompt
    EdgeTTSAPI ..> TechNewsSkill : note — TTS is separate (voice/tts.py)
```

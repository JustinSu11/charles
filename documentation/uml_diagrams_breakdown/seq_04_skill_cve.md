# Sequence Diagram 4 of 7 — Skill: CVE (NVD API)

Covers: how the CVE skill is triggered, the NVD API 2.0 query, parsing, and context injection. Triggered when the user's message contains "cve", "vulnerability", "exploit", "zero-day", "patch", or "security" with a recency signal.

```mermaid
sequenceDiagram
    participant Chat as POST /chat<br>(chat.py)
    participant SR as SkillRouter<br>(skill_router.py)
    participant CVE as CVE Skill<br>(cve.py)
    participant NVD as NVD API 2.0<br>(services.nvd.nist.gov)
    participant OR as OpenRouter API<br>(external)

    Chat ->> SR: route(message)
    Note over SR: Tier 1: "cve" anywhere in message<br>Tier 2: vuln vocab + recency word<br>("vulnerability"/"exploit"/"zero-day" + "latest"/"new"/etc.)<br>Tier 3: "security" + recency word
    SR -->> Chat: ["cve"]

    Chat ->> CVE: run_skill("cve", message)
    CVE ->> CVE: compute pubStartDate = now - 7 days<br>compute pubEndDate = now (UTC)

    alt NVD_API_KEY configured
        CVE ->> NVD: GET /rest/json/cves/2.0<br>?pubStartDate=...&pubEndDate=...&resultsPerPage=10<br>Header: apiKey<br>Rate limit: 50 req / 30 s
    else No API key
        CVE ->> NVD: GET /rest/json/cves/2.0<br>?pubStartDate=...&pubEndDate=...&resultsPerPage=10<br>Rate limit: 5 req / 30 s (unauthenticated)
    end

    NVD -->> CVE: JSON {vulnerabilities: [...]}

    loop For each CVE entry (up to 10)
        CVE ->> CVE: _parse_cve(cve)<br>Extract: id, description (en),<br>CVSS v3.1 score + severity
    end

    CVE ->> CVE: sort by severity (CRITICAL → HIGH → MEDIUM → LOW)
    CVE -->> Chat: skill_context block:<br>CVE IDs, severity labels,<br>CVSS scores, descriptions

    Chat ->> OR: POST /chat/completions<br>{history, system_prompt + skill_context}
    Note over OR: Voice brevity prompt active:<br>LLM leads with top 2-3 critical CVEs
    OR -->> Chat: reply summarising most severe CVEs
```

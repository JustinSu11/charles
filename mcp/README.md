# mcp/

MCP (Model Context Protocol) server implementations for Charles.

## Planned servers

### `virustotal/`

Scan URLs, look up file hashes, check for credential leaks via the VirusTotal API.

- Rate limit: 4 requests/min (free tier)
- Env: `VIRUSTOTAL_API_KEY`

### `vulnerability/`

Search vulnerability databases (NVD, CVE Details, OSV, Vulners) by keyword, CVE ID, or severity.

- Env: `CVE_API_KEY` (if required by chosen source)

### `technews/`

Fetch and filter tech/security headlines from NewsAPI and similar sources.

- Env: `NEWS_API_KEY`

## MCP protocol

Each server exposes a standard MCP interface consumed by the Charles API via `api/mcp_client.py`.

## Existing code

`src/cve_wrapper.py` in the repo root contains early CVE integration work — it will be migrated into `mcp/vulnerability/` during Phase 2.

"""
cve.py — NVD (National Vulnerability Database) skill for Charles.

Surfaces recent CVEs so Charles can brief on the latest security vulnerabilities.
Uses the NVD REST API 2.0 directly (no third-party library needed).

Skill anatomy: see tech_news.py for full explanation.
"""

import os
import httpx
from datetime import datetime, timedelta, timezone

# ── Tier 1: always loaded (keep short) ───────────────────────────────────────

DESCRIPTION = "Fetch and summarise recent CVEs from the National Vulnerability Database."

# ── Tier 2: only loaded when triggered ───────────────────────────────────────

INSTRUCTIONS = """
You have access to recently published CVEs (Common Vulnerabilities and Exposures)
from the National Vulnerability Database, provided below.

When answering a question about security vulnerabilities or CVEs:
- Lead with the most severe vulnerabilities (CRITICAL or HIGH CVSS score) first
- Always mention the CVE ID (e.g. CVE-2025-12345) so the user can look it up
- State the CVSS severity label (CRITICAL / HIGH / MEDIUM / LOW) and score
- Give a plain-English one-sentence description of what the vulnerability is
- If the user is on voice, mention 2-3 of the most critical ones by name and severity
- Do not speculate about exploitability beyond what the description says
- If asked about a specific CVE not in the list, say you only have today's recent batch
""".strip()

# ── Fetch ─────────────────────────────────────────────────────────────────────

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_CVE_LIMIT = 10     # how many recent CVEs to fetch
_DAYS_BACK = 7      # look back this many days for "recent" CVEs


async def fetch() -> list[dict]:
    """
    Fetches the most recently published CVEs from the NVD API.
    Returns a list of parsed CVE dicts with id, description, severity, and score.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=_DAYS_BACK)

    # NVD expects this exact ISO format (no microseconds, Z suffix)
    fmt = "%Y-%m-%dT%H:%M:%S.000"
    params = {
        "pubStartDate":   start.strftime(fmt),
        "pubEndDate":     now.strftime(fmt),
        "resultsPerPage": _CVE_LIMIT,
    }

    headers = {}
    api_key = os.getenv("NVD_API_KEY")
    if api_key:
        headers["apiKey"] = api_key

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(NVD_BASE, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    raw_vulns = data.get("vulnerabilities", [])
    return [_parse_cve(v["cve"]) for v in raw_vulns if "cve" in v]


def _parse_cve(cve: dict) -> dict:
    """
    Flattens the deeply nested NVD CVE object into a simple dict.
    The raw structure is: cve.descriptions[], cve.metrics.cvssMetricV31[].cvssData
    """
    # English description (fall back to first available)
    descriptions = cve.get("descriptions", [])
    english = next((d["value"] for d in descriptions if d.get("lang") == "en"), "No description available.")

    # CVSS v3.1 score and severity (dig through the nesting)
    score    = None
    severity = "UNKNOWN"
    metrics  = cve.get("metrics", {})

    for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(metric_key, [])
        if entries:
            cvss_data = entries[0].get("cvssData", {})
            score     = cvss_data.get("baseScore")
            severity  = cvss_data.get("baseSeverity", "UNKNOWN")
            break

    return {
        "id":          cve.get("id", "CVE-UNKNOWN"),
        "published":   cve.get("published", ""),
        "description": english,
        "score":       score,
        "severity":    severity,
    }


# ── Format ────────────────────────────────────────────────────────────────────

# Severity order for sorting: most dangerous first
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}


def format(cves: list[dict]) -> str:
    """
    Converts parsed CVE dicts into a readable context block.
    Sorted by severity so the LLM naturally leads with the worst ones.
    """
    if not cves:
        return f"No CVEs published in the last {_DAYS_BACK} days could be retrieved."

    # Sort: critical first, then by score descending within each tier
    sorted_cves = sorted(
        cves,
        key=lambda c: (_SEVERITY_ORDER.get(c["severity"], 4), -(c["score"] or 0)),
    )

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines = [f"## Recent CVEs — Last {_DAYS_BACK} Days ({today})\n"]

    for i, cve in enumerate(sorted_cves, 1):
        score_str = f"{cve['score']}" if cve["score"] is not None else "N/A"
        lines.append(
            f"{i}. **{cve['id']}** — {cve['severity']} (CVSS {score_str})\n"
            f"   {cve['description']}\n"
        )

    return "\n".join(lines)

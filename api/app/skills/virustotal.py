"""
virustotal.py — VirusTotal skill for Charles.

Looks up a file hash or URL against the VirusTotal API v3 and returns a
plain-text verdict the LLM can summarise for the user.

Requires:
    VIRUSTOTAL_API_KEY in .env  (free tier at https://www.virustotal.com/gui/sign-in)

Supported inputs (extracted from the user's message):
    File hash: MD5 (32 hex), SHA-1 (40 hex), SHA-256 (64 hex)
    URL: any string starting with http:// or https://

Skill anatomy: see tech_news.py for full explanation.
"""

from __future__ import annotations

import base64
import os
import re
from datetime import datetime
from typing import Optional

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

_API_KEY: str = os.getenv("VIRUSTOTAL_API_KEY", "")
_BASE = "https://www.virustotal.com/api/v3"
_HEADERS = {"x-apikey": _API_KEY}

# ── Tier 1: always loaded (keep short) ───────────────────────────────────────

DESCRIPTION = "Look up file hashes or URLs on VirusTotal and report whether they are malicious."

# ── Tier 2: only loaded when triggered ───────────────────────────────────────

INSTRUCTIONS = """
You can help the user check whether a file or URL is malicious using VirusTotal.

VirusTotal accepts three kinds of targets:
  - File hash: MD5 (32 hex chars), SHA-1 (40 hex chars), or SHA-256 (64 hex chars)
  - URL: any full URL starting with http:// or https://
  - Domain: a bare domain like malware.example.com

If live scan data is provided below, use it to give a clear verdict:
  - Lead with SAFE, SUSPICIOUS, or MALICIOUS
  - State the detection ratio (e.g. "3 of 72 engines flagged this")
  - For MALICIOUS/SUSPICIOUS: mention what the engines called it
  - For SAFE: reassure the user but note it is not a 100% guarantee

If NO live scan data is provided (no API key configured), tell the user you can't
run the check yourself because no VirusTotal API key is configured, then give
them the direct link so they can check it themselves:
    File hash → https://www.virustotal.com/gui/file/{hash}/detection
    URL       → https://www.virustotal.com/gui/url-search?query={url}
    Domain    → https://www.virustotal.com/gui/domain/{domain}/detection
If no hash or URL was provided either, let them know you'd need both a key and
a target to help — ask them for the hash or URL and mention the key limitation.

If the user asks how to get a file hash:
  - Windows: certutil -hashfile <file> SHA256
  - macOS/Linux: shasum -a 256 <file>
""".strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_target(message: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extract a hash or URL from the user's message.

    Returns (target, kind) where kind is "hash" or "url", or (None, None).
    """
    # SHA-256 (64 hex chars) — check longest first to avoid partial matches
    m = re.search(r'\b([0-9a-fA-F]{64})\b', message)
    if m:
        return m.group(1).lower(), "hash"

    # SHA-1 (40 hex chars)
    m = re.search(r'\b([0-9a-fA-F]{40})\b', message)
    if m:
        return m.group(1).lower(), "hash"

    # MD5 (32 hex chars)
    m = re.search(r'\b([0-9a-fA-F]{32})\b', message)
    if m:
        return m.group(1).lower(), "hash"

    # URL
    m = re.search(r'https?://\S+', message)
    if m:
        return m.group(0).rstrip('.,;)"\''), "url"

    return None, None


def _verdict(stats: dict) -> str:
    malicious   = stats.get("malicious", 0)
    suspicious  = stats.get("suspicious", 0)
    harmless    = stats.get("harmless", 0)
    undetected  = stats.get("undetected", 0)
    total = malicious + suspicious + harmless + undetected
    if malicious > 0:
        return f"MALICIOUS ({malicious}/{total} engines flagged)"
    if suspicious > 0:
        return f"SUSPICIOUS ({suspicious}/{total} engines flagged)"
    return f"SAFE (0/{total} engines flagged)"


def _top_labels(analysis_results: dict, limit: int = 5) -> list[str]:
    """Return the most common malware label strings from flagging engines."""
    labels: dict[str, int] = {}
    for engine_result in analysis_results.values():
        if engine_result.get("category") in ("malicious", "suspicious"):
            label = engine_result.get("result") or ""
            if label:
                labels[label] = labels.get(label, 0) + 1
    return [lbl for lbl, _ in sorted(labels.items(), key=lambda x: -x[1])[:limit]]


# ── Fetch ─────────────────────────────────────────────────────────────────────

async def fetch(message: str = "") -> Optional[dict]:
    """
    Extract a hash or URL from *message* and look it up on VirusTotal.

    Returns a result dict, or None if no hash/URL is found in the message.

    When no API key is configured, returns a sentinel dict with
    ``no_key=True`` so ``format()`` injects a hard factual "NO SCAN
    PERFORMED" block.  This is stronger than returning None (instructions
    only) because LLMs treat data-block statements as facts they must not
    contradict — preventing them from hallucinating scan results from
    training data.
    """
    if not _API_KEY:
        target, kind = _extract_target(message)
        return {"no_key": True, "target": target, "kind": kind}

    target, kind = _extract_target(message)

    if target is None:
        # No target in message — return None so INSTRUCTIONS are injected and
        # the LLM asks the user to provide a hash or URL.
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if kind == "hash":
                resp = await client.get(f"{_BASE}/files/{target}", headers=_HEADERS)
            else:
                # VT URL lookup requires base64url-encoding (no padding)
                encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
                resp = await client.get(f"{_BASE}/urls/{encoded}", headers=_HEADERS)

            if resp.status_code == 404:
                return {"error": f"'{target}' was not found in VirusTotal's database. "
                                  "It may be a new or very rare file."}
            if resp.status_code == 401:
                return {"error": "VirusTotal API key is invalid or expired."}
            if resp.status_code == 429:
                return {"error": "VirusTotal rate limit reached. Try again in a minute."}

            resp.raise_for_status()
            data = resp.json()

        except httpx.TimeoutException:
            return {"error": "VirusTotal API timed out."}

    attrs   = data.get("data", {}).get("attributes", {})
    stats   = attrs.get("last_analysis_stats", {})
    results = attrs.get("last_analysis_results", {})

    # Timestamp
    ts = attrs.get("last_analysis_date") or attrs.get("last_submission_date")
    scanned_at = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "unknown date"

    return {
        "target":     target,
        "kind":       kind,
        "verdict":    _verdict(stats),
        "stats":      stats,
        "labels":     _top_labels(results),
        "scanned_at": scanned_at,
        "name":       attrs.get("meaningful_name") or attrs.get("url") or target,
    }


# ── Format ────────────────────────────────────────────────────────────────────

def format(data: dict) -> str:
    # No API key — produce a hard factual statement the LLM cannot contradict.
    # Do NOT return instructions here; the INSTRUCTIONS block already handles
    # the "what to tell the user" guidance.  This block provides the facts.
    if data.get("no_key"):
        target = data.get("target")
        kind   = data.get("kind")
        if target and kind == "hash":
            link = f"https://www.virustotal.com/gui/file/{target}/detection"
        elif target and kind == "url":
            link = f"https://www.virustotal.com/gui/url-search?query={target}"
        else:
            link = "https://www.virustotal.com"
        lines = [
            "=== VirusTotal: NO SCAN PERFORMED ===",
            "VIRUSTOTAL_API_KEY is not configured in Charles.",
            "A real-time API call was NOT made. No scan data exists.",
            "Do NOT present scan statistics, verdicts, or engine results.",
        ]
        if target:
            lines.append(f"Target identified in message: {target}")
        lines.append(f"Direct link for the user to check themselves: {link}")
        return "\n".join(lines)

    if "error" in data:
        return f"VirusTotal lookup failed: {data['error']}"

    lines = [
        f"=== VirusTotal Result ===",
        f"Target   : {data['name']}",
        f"Verdict  : {data['verdict']}",
        f"Scanned  : {data['scanned_at']}",
    ]

    stats = data["stats"]
    total = sum(stats.get(k, 0) for k in ("malicious", "suspicious", "harmless", "undetected"))
    lines.append(
        f"Engines  : {stats.get('malicious',0)} malicious, "
        f"{stats.get('suspicious',0)} suspicious, "
        f"{stats.get('harmless',0)} harmless, "
        f"{stats.get('undetected',0)} undetected  (of {total} total)"
    )

    if data["labels"]:
        lines.append(f"Labels   : {', '.join(data['labels'])}")

    vt_url = (
        f"https://www.virustotal.com/gui/file/{data['target']}/detection"
        if data["kind"] == "hash"
        else f"https://www.virustotal.com/gui/url-search?query={data['target']}"
    )
    lines.append(f"Full report: {vt_url}")

    return "\n".join(lines)

"""
virustotal.py — VirusTotal skill for Charles.

This is an instructional-only skill: fetch() returns None, meaning no live
API call is made. Instead, INSTRUCTIONS teaches the LLM how to handle
VirusTotal queries conversationally — extract the target from the message,
ask for it if missing, and construct direct VT links the user can open.

Why no live API call?
  VirusTotal queries are targeted (a specific hash or URL), not ambient
  ("what's out there?"). Rather than scanning something the user hasn't
  explicitly confirmed, we let the LLM guide the conversation and surface
  a direct VirusTotal link. The user stays in control.

Skill anatomy: see tech_news.py for full explanation.
"""

# ── Tier 1: always loaded (keep short) ───────────────────────────────────────

DESCRIPTION = "Guide users to check file hashes or URLs against VirusTotal."

# ── Tier 2: only loaded when triggered ───────────────────────────────────────

INSTRUCTIONS = """
You can help the user check whether a file or URL is malicious using VirusTotal.

VirusTotal accepts three kinds of targets:
  - File hash: MD5 (32 hex chars), SHA-1 (40 hex chars), or SHA-256 (64 hex chars)
  - URL: any full URL starting with http:// or https://
  - Domain: a bare domain like malware.example.com

How to handle a VirusTotal request:

1. If the user's message already contains a hash or URL, construct the direct
   VirusTotal link and present it:
     File hash → https://www.virustotal.com/gui/file/{hash}/detection
     URL       → https://www.virustotal.com/gui/url-search?query={url}
     Domain    → https://www.virustotal.com/gui/domain/{domain}/detection

2. If the user has NOT provided a target yet, ask them for it clearly.
   On voice, say something like: "What's the file hash or URL you'd like me
   to check?" — keep it short, the user is probably reading from a terminal.

3. Never guess or fabricate scan results. You don't have API access to
   VirusTotal scan data — only the user clicking the link will see results.

4. If the user asks what a hash is or how to get one, briefly explain:
   - On Windows: certutil -hashfile <file> SHA256
   - On macOS/Linux: shasum -a 256 <file>
""".strip()

# ── Fetch (instructional-only — no data needed) ───────────────────────────────

async def fetch() -> None:
    """
    This skill has no live data to fetch.
    Returning None signals run_skill() to inject INSTRUCTIONS only.
    """
    return None


# ── Format (unreachable for this skill, included for interface consistency) ───

def format(data: None) -> str:
    return ""

"""
tech_news.py — Hacker News skill for Charles.

Skill anatomy (read this if you're new to AI skills):
─────────────────────────────────────────────────────
  DESCRIPTION   Always in system prompt. One line. Keep it under ~15 words.
                The LLM uses this to know the skill exists.

  INSTRUCTIONS  Only injected when this skill is triggered. This is where
                you write natural language instructions to the LLM — not
                code, but guidance: how to tone the response, what to
                emphasise, what to skip. This is the "AI programming" part.

  fetch()       Async function that calls the external API and returns raw
                data. Runs only when triggered — no wasted API calls.

  format()      Turns raw data into a readable context block the LLM can
                reason over. Think of it as serialising data into prose.
─────────────────────────────────────────────────────
"""

import asyncio
import httpx
from datetime import datetime, timezone

# ── Tier 1: always loaded (keep short) ───────────────────────────────────────

DESCRIPTION = "Fetch and summarise the latest trending stories from Hacker News."

# ── Tier 2: only loaded when triggered ───────────────────────────────────────

INSTRUCTIONS = """
You have access to today's top stories from Hacker News, provided below.

When answering a question about tech news or current events in tech:
- Lead with the most relevant or interesting story rather than listing everything
- Include the story title and score so the user knows how popular it is
- Mention the discussion count (comments) when it signals high community interest
- Keep your response conversational — you're briefing someone, not reading a list
- If the user is using voice, pick the top 2-3 stories and describe them naturally
- If the user asks for more detail on a specific story, note that you can only see
  the headline and metadata — you do not have the full article content
""".strip()

# ── Fetch ─────────────────────────────────────────────────────────────────────

HN_BASE = "https://hacker-news.firebaseio.com/v0"
_STORY_LIMIT = 10   # how many top stories to fetch


async def fetch() -> list[dict]:
    """
    Fetches the top N stories from Hacker News.
    Uses parallel requests — HN requires one HTTP call per story item.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: get the ranked list of story IDs
        resp = await client.get(f"{HN_BASE}/topstories.json")
        resp.raise_for_status()
        top_ids = resp.json()[:_STORY_LIMIT]

        # Step 2: fetch all story details in parallel
        tasks = [client.get(f"{HN_BASE}/item/{sid}.json") for sid in top_ids]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    stories = []
    for r in responses:
        if isinstance(r, Exception):
            continue
        try:
            item = r.json()
            if item and item.get("type") == "story":
                stories.append(item)
        except Exception:
            continue

    return stories


# ── Format ────────────────────────────────────────────────────────────────────

def format(stories: list[dict]) -> str:
    """
    Converts raw HN story objects into a readable context block.
    The LLM reads this text to answer news questions — structure matters.
    """
    if not stories:
        return "No stories could be retrieved from Hacker News at this time."

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines = [f"## Hacker News — Top Stories ({today})\n"]

    for i, story in enumerate(stories, 1):
        title    = story.get("title", "Untitled")
        url      = story.get("url", "news.ycombinator.com")
        score    = story.get("score", 0)
        comments = story.get("descendants", 0)
        author   = story.get("by", "unknown")

        lines.append(
            f"{i}. **{title}**\n"
            f"   Score: {score} pts · {comments} comments · by {author}\n"
            f"   {url}\n"
        )

    return "\n".join(lines)

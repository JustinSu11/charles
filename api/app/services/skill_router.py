"""
skill_router.py — Decides which skills to activate for a given user message.

This is intentionally kept separate from the skills themselves so the
routing strategy can evolve independently (e.g. swap keyword matching for
a lightweight embedding classifier) without touching skill logic.

How it fits in the request pipeline:
  chat.py receives message
      ↓
  skill_router.route(message) → ["tech_news"]
      ↓
  For each activated skill: fetch live data, inject full instructions
      ↓
  LLM call with enriched context
"""

from api.app.skills import SKILLS

# ── Trigger map ───────────────────────────────────────────────────────────────
# Maps skill name → the function that decides whether to activate it.
# Each function receives the normalised (lowercase, stripped) message and
# returns True if the skill should run.
#
# TODO (user contribution): implement `_should_fetch_news` below.

def _should_fetch_news(message: str) -> bool:
    # Direct source mentions — always a news request
    if "hacker news" in message or " hn " in message:
        return True

    # "news" paired with a tech/recency context word
    if "news" in message:
        context_words = {"tech", "latest", "today", "recent", "trending", "dev"}
        return any(word in message for word in context_words)

    # Trending/latest without "news" — e.g. "what's trending in tech?"
    if "trending" in message or "latest" in message:
        context_words = {"tech", "dev", "programming", "cyber", "software", "technology", "ai", "machine learning"}
        return any(word in message for word in context_words)

    return False


_TRIGGER_MAP: dict[str, callable] = {
    "tech_news": _should_fetch_news,
}

# ── Router ────────────────────────────────────────────────────────────────────

def route(message: str) -> list[str]:
    """
    Returns the list of skill names that should be activated for this message.
    Only skills present in both SKILLS and _TRIGGER_MAP are considered.
    """
    normalised = message.lower().strip()
    return [
        name
        for name, should_activate in _TRIGGER_MAP.items()
        if name in SKILLS and should_activate(normalised)
    ]

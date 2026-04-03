"""
skills/__init__.py — Skill registry for Charles.

A "skill" is a self-contained capability module with three parts:
  1. DESCRIPTION  — one line, always included in every system prompt
  2. INSTRUCTIONS — full prompt injected only when the skill is triggered
  3. fetch()      — retrieves live external data the LLM needs

The registry here is the single source of truth for which skills exist.
chat.py uses it to:
  - Build the base system prompt (descriptions only, always cheap)
  - Decide which skills to activate per query (via skill_router)
  - Inject full instructions + fetched data only for active skills
"""

from api.app.skills import tech_news

# ── Registry ──────────────────────────────────────────────────────────────────
# Maps skill name → module. Add new skills here and nowhere else.
SKILLS: dict = {
    "tech_news": tech_news,
}


def get_skill_index() -> str:
    """
    Returns a compact index of all skills for injection into the base system
    prompt. Always loaded — must stay short (one line per skill).

    Example output:
        Available skills (activated automatically when relevant):
        - tech_news: Latest stories from Hacker News
    """
    lines = ["Available skills (activated automatically when relevant):"]
    for name, module in SKILLS.items():
        lines.append(f"- {name}: {module.DESCRIPTION}")
    return "\n".join(lines)


async def run_skill(name: str) -> str:
    """
    Fetches live data for a skill and returns a formatted context block
    ready to be injected into the system prompt.

    Includes both the full INSTRUCTIONS and the fetched data so the LLM
    knows both *how* to respond and *what* to respond with.
    """
    module = SKILLS[name]
    data = await module.fetch()
    return f"{module.INSTRUCTIONS}\n\n{module.format(data)}"

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v3.2")

BASE_SYSTEM_PROMPT = (
    "You are Charles, a helpful AI assistant. "
    "You are concise, accurate, and security-aware. "
    "When asked about vulnerabilities or security topics, be thorough but clear."
)

VOICE_BREVITY_PROMPT = (
    "IMPORTANT: This request came from the voice interface. "
    "Keep your reply to 2-3 sentences maximum — short enough to speak aloud naturally. "
    "Lead with the single most important point. "
    "The full details are visible in the GUI, so do not try to list everything."
)


async def get_openrouter_response(
    conversation_history: list[dict],
    model: str | None = None,
    skill_context: str | None = None,
    interface: str = "web",
) -> str:
    """
    Send conversation history to OpenRouter and return the assistant reply.

    Args:
        conversation_history: List of {"role": ..., "content": ...} dicts
                               representing the full conversation so far.
        model: OpenRouter model ID to use (e.g. "openai/gpt-4o").
               Falls back to the OPENROUTER_MODEL env var if not provided.
        skill_context: Pre-fetched skill data to inject into the system prompt.
        interface: "voice" or "web" — voice requests get a brevity instruction
                   so the LLM generates short speakable responses.
    Returns:
        The assistant's reply as a plain string.
    Raises:
        httpx.HTTPStatusError: On 4xx/5xx from OpenRouter (rate limits, auth failures).
        httpx.TimeoutException: If OpenRouter takes too long to respond.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in environment")

    from app.skills import get_skill_index
    system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + get_skill_index()
    if interface == "voice":
        system_prompt += "\n\n" + VOICE_BREVITY_PROMPT
    if skill_context:
        system_prompt += "\n\n" + skill_context

    messages = [{"role": "system", "content": system_prompt}] + conversation_history

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        # required by OpenRouter
        "X-Title": "Charles AI Assistant",
    }

    payload = {
        "model": model or MODEL,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)
        response.raise_for_status() #throws HTTPStatus Error on 4xx/5xx
    
    data = response.json()
    return data["choices"][0]["message"]["content"]
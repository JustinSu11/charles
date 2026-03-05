import httpx
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

SYSTEM_PROMPT = (
    "You are Charles, a helpful AI assistant. "
    "You are concise, accurate, and security-aware. "
    "When asked about vulnerabilities or security topics, be thorough but clear."
)

"""
Takes full conversation history so that the LLM has context for the whole conversation.
"""
async def get_openrouter_response(conversation_history: list[dict]) -> str:
    """
    Send conversation history to OpenRouter and return the assistant reply.

    Args:
        conversation_history: List of {"role": ..., "content": ...} dicts
                               representing the full conversation so far.
    Returns:
        The assistant's reply as a plain string.
    Raises:
        httpx.HTTPStatusError: On 4xx/5xx from OpenRouter (rate limits, auth failures).
        httpx.TimeoutException: If OpenRouter takes too long to respond.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in environment")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        # required by OpenRouter
        "X-Title": "Charles AI Assistant",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)
        response.raise_for_status() #throws HTTPStatus Error on 4xx/5xx
    
    data = response.json()
    return data["choices"][0]["message"]["content"]
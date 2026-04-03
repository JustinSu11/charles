"""
settings.py — User-facing configuration endpoints.

GET  /settings/model  — return the currently active OpenRouter model ID
PUT  /settings/model  — persist a new model selection to app_state
GET  /models          — proxy OpenRouter's model catalogue (5-min TTL cache)
"""

import os
import time
from dotenv import load_dotenv

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

load_dotenv()

_DEFAULT_MODEL    = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v3.2")
_OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY")
_MODELS_CACHE_TTL = 300  # seconds

router = APIRouter()

# ── In-process model list cache ───────────────────────────────────────────────
_cached_models: list[dict]  = []
_cached_at:     float       = 0.0


class ModelSelection(BaseModel):
    model: str


# ── Active model ──────────────────────────────────────────────────────────────

@router.get("/settings/model")
async def get_active_model(db: AsyncSession = Depends(get_db)):
    """Return the currently selected model ID."""
    result = await db.execute(
        text("SELECT value FROM app_state WHERE key = 'active_model'")
    )
    row = result.fetchone()
    return {"model": row[0] if row else _DEFAULT_MODEL}


@router.put("/settings/model")
async def set_active_model(body: ModelSelection, db: AsyncSession = Depends(get_db)):
    """Persist the selected model to app_state (upsert)."""
    await db.execute(
        text("""
            INSERT INTO app_state (key, value) VALUES ('active_model', :model)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """),
        {"model": body.model},
    )
    await db.commit()
    return {"model": body.model}


# ── Model catalogue ───────────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    """
    Return the models available on this OpenRouter account.

    Results are cached for 5 minutes to avoid hammering the OpenRouter API.
    Falls back to the stale cache (or an empty list) if the request fails.
    """
    global _cached_models, _cached_at

    now = time.monotonic()
    if _cached_models and (now - _cached_at) < _MODELS_CACHE_TTL:
        return {"models": _cached_models}

    if not _OPENROUTER_KEY:
        return {"models": _cached_models}  # empty on first call, stale on retry

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {_OPENROUTER_KEY}"},
            )
            resp.raise_for_status()

        data = resp.json().get("data", [])
        models = sorted(
            [
                {"id": m["id"], "name": m.get("name", m["id"])}
                for m in data
                if m.get("context_length", 0) > 0
            ],
            key=lambda m: m["id"],
        )
        _cached_models = models
        _cached_at = now
    except Exception:
        pass  # keep serving stale cache

    return {"models": _cached_models}

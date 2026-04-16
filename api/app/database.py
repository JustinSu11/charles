"""
database.py — SQLite async engine and session factory.

DB file lives at ~/.charles/charles.db by default.
Override with DATABASE_URL or CHARLES_DATA_DIR env vars.
"""

import os
import pathlib

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv

# When running packaged, Electron passes CHARLES_DATA_DIR pointing to userData.
# Load .env from there first (override=False so real env vars always win),
# then fall back to CWD/.env for dev mode.
_env_data_dir = os.environ.get("CHARLES_DATA_DIR")
if _env_data_dir:
    load_dotenv(pathlib.Path(_env_data_dir) / ".env", override=False)
load_dotenv()  # dev fallback (CWD / project root)

# Resolve DB file path
_data_dir = pathlib.Path(
    os.environ.get("CHARLES_DATA_DIR", pathlib.Path.home() / ".charles")
)
_data_dir.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{_data_dir / 'charles.db'}"
)

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session, closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session


async def ping_db() -> bool:
    """Returns True if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

"""
conftest.py — test fixtures for the Charles API.
Uses in-memory SQLite and mocks the OpenRouter call.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from app.main import app
from app.database import get_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

DDL = [
    """CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY, interface TEXT NOT NULL DEFAULT 'voice',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS app_state (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""",
]


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        for stmt in DDL:
            await conn.execute(text(stmt))
        # Pre-test cleanup ensures a previous test's dirty state doesn't leak in
        for tbl in ("messages", "conversations", "app_state"):
            await conn.execute(text(f"DELETE FROM {tbl}"))
    yield
    async with test_engine.begin() as conn:
        for tbl in ("messages", "conversations", "app_state"):
            await conn.execute(text(f"DELETE FROM {tbl}"))


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def patched_openrouter():
    """Yields a controllable AsyncMock for get_openrouter_response."""
    mock = AsyncMock(return_value="mocked reply")
    with patch("app.routers.chat.get_openrouter_response", new=mock):
        yield mock

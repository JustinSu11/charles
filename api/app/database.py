from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlachemy import text
from dotenv import load_dotenv
import os

load_dotenv()

#asyncpg driver for async SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://charles:charles@postgres:5432/charles")

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# FastAPI dependency — yields a DB session, closes it after the request.
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# Health check — returns True if PostgreSQL is reachable.
async def ping_db():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
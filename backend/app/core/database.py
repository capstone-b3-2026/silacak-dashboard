import asyncpg

from app.core.config import settings

pool: asyncpg.Pool | None = None


async def connect_db() -> None:
    global pool
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=10)


async def disconnect_db() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def get_db():
    """FastAPI dependency: kasih satu connection dari pool per-request."""
    async with pool.acquire() as conn:
        yield conn

"""Async Postgres engine and sessions."""
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool

from mux.config import settings

# asyncpg caches prepared statements per connection. Supabase's transaction pooler (port 6543) hands each
# transaction a different server connection, so a cached statement goes missing and queries fail (Q43).
# With the cache off the engine works on the session pooler, the transaction pooler, and plain Postgres.
_CONNECT_ARGS = {"statement_cache_size": 0}


def make_engine(url: str, poolclass: type[Pool] | None = None) -> AsyncEngine:
    """Build an asyncpg engine for Supabase's pooler (small pool, DB13)."""
    if poolclass is not None:
        return create_async_engine(url, poolclass=poolclass, connect_args=_CONNECT_ARGS)
    return create_async_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True, connect_args=_CONNECT_ARGS)

@lru_cache
def get_engine() -> AsyncEngine:
    """The process-wide engine, created on first use from 'settings.database_url'."""
    return make_engine(settings.database_url)

@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """The process-wide session factory."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)

async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session that is closed on exit (FastAPI dependency)."""
    async with get_sessionmaker()() as session:
        yield session

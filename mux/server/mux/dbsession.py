"""Async Postgres engine and sessions."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from mux.config import settings

logger = logging.getLogger(__name__)

# Global engine and session factory
engine: AsyncEngine | None = None
async_session_maker: sessionmaker | None = None


async def init_db() -> None:
    """Initialize the database engine and create tables."""
    global engine, async_session_maker

    if engine is not None:
        logger.warning("Database already initialized")
        return

    # Use SQLite for development if no database_url is set
    database_url = settings.database_url or "sqlite+aiosqlite:///./mux.db"

    # Convert postgres:// to postgresql+asyncpg:// for async
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    logger.info(f"Initializing database: {database_url}")

    engine = create_async_engine(
        database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create tables (in production, use Alembic migrations)
    # await create_tables()
    logger.info("Database initialized")


async def close_db() -> None:
    """Close the database engine."""
    global engine, async_session_maker
    if engine is not None:
        await engine.dispose()
        engine = None
        async_session_maker = None
        logger.info("Database connections closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session_direct() -> AsyncSession:
    """Get a database session directly (caller must close)."""
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return async_session_maker()
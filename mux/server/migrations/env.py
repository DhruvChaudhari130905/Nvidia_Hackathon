import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from mux.config import settings
from mux.db.session import make_engine
from mux.db.tables import Base

config = context.config
target_metadata = Base.metadata

def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.database_url

def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def _run_async() -> None:
    engine = make_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()

def run_migrations_online() -> None:
    asyncio.run(_run_async())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

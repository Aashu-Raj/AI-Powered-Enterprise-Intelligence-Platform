"""
database/session.py

Async SQLAlchemy engine and session factory.
Use get_async_session() as an async context manager / FastAPI dependency.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config.settings import settings

# ── Engine ───────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.app_debug,          # log SQL in dev
    pool_size=10,                     # max persistent connections
    max_overflow=20,                  # extra connections beyond pool_size
    pool_pre_ping=True,               # verify connection health before use
    pool_recycle=3600,                # recycle connections every 1h
)

# ── Session Factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,           # avoid lazy-load errors post-commit
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for a database session.

    Usage:
        async with get_async_session() as session:
            result = await session.execute(select(User))

    Also usable as a FastAPI dependency via Depends().
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for injecting an async DB session.

    Usage in FastAPI route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_async_session() as session:
        yield session

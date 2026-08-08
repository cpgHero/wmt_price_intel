"""Async SQLAlchemy engine lifecycle and readiness checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def normalize_database_url(database_url: str) -> str:
    """Select psycopg's async SQLAlchemy dialect for standard Postgres URLs."""

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class DatabaseProbe:
    """Own one lazy connection pool and expose a bounded readiness probe."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            normalize_database_url(database_url),
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": 3},
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def is_ready(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def async_postgres_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


class Database:
    def __init__(self, dsn: str) -> None:
        self.engine = create_async_engine(async_postgres_dsn(dsn))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session, session.begin():
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()

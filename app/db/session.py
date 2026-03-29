from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# Этот модуль хранит process-wide SQLAlchemy engine и фабрику async sessions.
# Он является общей точкой доступа к БД для API, workers и projection layer.
settings = get_settings()
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    # FastAPI dependency отдает одну AsyncSession на запрос. Коммиты и rollbacks
    # выполняются уже на уровне вызывающих сервисов/handlers, а не автоматически здесь.
    async with SessionLocal() as session:
        yield session

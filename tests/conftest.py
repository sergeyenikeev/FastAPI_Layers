from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.runtime import AppRuntime


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    # Для тестов используется in-memory SQLite, чтобы быстро проверять
    # orchestration/query/projection flow без внешнего PostgreSQL контейнера.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
def test_settings() -> Settings:
    # Settings переопределяются под тестовый контур: in-memory БД, test API key,
    # локальный JWT secret и отключенный production-specific runtime noise.
    return Settings(
        APP_ENV="test",
        DEBUG=False,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        API_KEYS=["test-key"],
        JWT_SECRET="test-secret-key-with-32-bytes-minimum",
        KAFKA_BOOTSTRAP_SERVERS=["localhost:9092"],
        PROMETHEUS_ENABLED=True,
    )


@pytest_asyncio.fixture
async def runtime(
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> AsyncIterator[AppRuntime]:
    # Тестовый runtime собирается так же, как production runtime, но с test
    # settings и in-memory publisher. Это keeps wiring максимально реалистичным.
    runtime = AppRuntime(test_settings, session_factory=session_factory, engine_override=db_engine)
    await runtime.startup()
    yield runtime
    await runtime.shutdown()


@pytest_asyncio.fixture
async def client(runtime: AppRuntime) -> AsyncIterator[AsyncClient]:
    # Фикстура клиента подменяет get_runtime/get_settings и session dependency,
    # чтобы HTTP-тесты проходили через настоящий FastAPI app, но на test runtime.
    import app.core.security as security_module
    import app.main
    import app.runtime as runtime_module

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with runtime.session_factory() as session:
            yield session

    runtime_module.get_runtime = lambda: runtime  # type: ignore[assignment]
    app.main.get_runtime = lambda: runtime  # type: ignore[assignment]
    security_module.get_settings = lambda: runtime.settings  # type: ignore[assignment]

    app_instance = create_app()
    app_instance.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

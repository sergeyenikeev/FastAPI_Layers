from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.openapi import OPENAPI_TAGS
from app.api.router import build_api_router
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.core.middleware import CorrelationMiddleware, RateLimitStubMiddleware
from app.core.observability import setup_telemetry
from app.db.session import engine
from app.modules.monitoring.schemas import HealthSummary
from app.runtime import AppRuntime


def create_service_app(
    *,
    title: str,
    description: str,
    settings: Settings,
    runtime: AppRuntime,
    modules: Sequence[str],
) -> FastAPI:
    # Общая фабрика гарантирует, что все сервисы используют одинаковые middleware,
    # error contract, telemetry и системные endpoint-ы, даже если бизнес-роуты у
    # них отличаются. Так микросервисы сохраняют единый operational baseline.
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime
        await runtime.startup()
        yield
        await runtime.shutdown()

    tag_names = list(dict.fromkeys([*modules, "monitoring"]))
    tags = [OPENAPI_TAGS[name] for name in tag_names if name in OPENAPI_TAGS]
    app = FastAPI(
        title=title,
        version="0.1.0",
        description=description,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=tags,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimitStubMiddleware)
    install_error_handlers(app)
    setup_telemetry(app, engine, settings)
    app.include_router(build_api_router(modules), prefix=settings.api_v1_prefix)

    @app.get(
        "/metrics",
        include_in_schema=True,
        tags=["monitoring"],
        summary="Получить Prometheus-метрики сервиса",
        description=(
            "Возвращает runtime-метрики текущего микросервиса в формате Prometheus."
        ),
    )
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get(
        f"{settings.api_v1_prefix}/health/live",
        response_model=HealthSummary,
        tags=["monitoring"],
        summary="Проверка liveness сервиса",
        description="Минимальная проверка того, что процесс сервиса жив и отвечает.",
        operation_id=f"{settings.service_name}_health_live",
    )
    async def live() -> HealthSummary:
        return await runtime.health_service.live()

    @app.get(
        f"{settings.api_v1_prefix}/health/ready",
        response_model=HealthSummary,
        tags=["monitoring"],
        summary="Проверка readiness сервиса",
        description=(
            "Проверяет, может ли сервис обслуживать запросы и доступны ли его "
            "обязательные зависимости."
        ),
        operation_id=f"{settings.service_name}_health_ready",
    )
    async def ready() -> HealthSummary:
        async with runtime.session_factory() as session:
            return await runtime.health_service.ready(session)

    @app.get(
        f"{settings.api_v1_prefix}/health/deep",
        response_model=HealthSummary,
        tags=["monitoring"],
        summary="Глубокая проверка зависимостей сервиса",
        description=(
            "Расширенная проверка БД, Redis, Kafka, model probe-ов и worker heartbeat-ов."
        ),
        operation_id=f"{settings.service_name}_health_deep",
    )
    async def deep() -> HealthSummary:
        async with runtime.session_factory() as session:
            return await runtime.health_service.deep(session)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.service_name,
            "modules": ",".join(modules),
            "status": "ok",
        }

    return app

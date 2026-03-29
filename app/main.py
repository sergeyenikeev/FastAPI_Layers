from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import build_api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import CorrelationMiddleware, RateLimitStubMiddleware
from app.core.observability import setup_telemetry
from app.db.session import engine
from app.runtime import get_runtime

OPENAPI_TAGS = [
    {
        "name": "registry",
        "description": (
            "Группа ручек для управления реестровыми сущностями платформы. "
            "Здесь создаются и изменяются агенты, модели, графы, деплойменты, "
            "инструменты и окружения. Это основной командный вход для "
            "конфигурации платформы, а чтение идет только из materialized read models."
        ),
    },
    {
        "name": "orchestration",
        "description": (
            "Группа ручек для запуска и просмотра выполнений. "
            "Через эти эндпоинты создаются execution run, а затем читается их "
            "текущее и завершенное состояние вместе со списком шагов."
        ),
    },
    {
        "name": "monitoring",
        "description": (
            "Группа ручек для эксплуатационного мониторинга платформы. "
            "Включает health probes, выборку метрик, агрегированную performance summary, "
            "стоимость, аномалии и отчеты по дрейфу."
        ),
    },
    {
        "name": "alerting",
        "description": (
            "Группа ручек для просмотра алертов, сформированных аналитическими "
            "и operational контурами платформы. Используется операторами для "
            "контроля текущих инцидентов и подтверждения их статуса."
        ),
    },
    {
        "name": "audit",
        "description": (
            "Группа ручек для просмотра аудиторского следа. "
            "Позволяет восстановить, кто и когда инициировал изменение или запуск, "
            "и с какими correlation_id и trace_id это было связано."
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = get_runtime()
    await runtime.startup()
    yield
    await runtime.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Workflow Operations Platform",
        version="0.1.0",
        description=(
            "Централизованная платформа эксплуатации сценариев с event-driven архитектурой, "
            "CQRS, Kafka, PostgreSQL projections, мониторингом, аудитом и orchestration-слоем "
            "на базе LangGraph. Write-path публикует события, а HTTP API читает только read models."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimitStubMiddleware)
    install_error_handlers(app)
    setup_telemetry(app, engine, settings)
    app.include_router(build_api_router(), prefix=settings.api_v1_prefix)

    @app.get(
        "/metrics",
        include_in_schema=True,
        tags=["monitoring"],
        summary="Получить Prometheus-метрики приложения",
        description=(
            "Возвращает метрики приложения в формате Prometheus exposition. "
            "Ручка нужна для scrape со стороны Prometheus, ServiceMonitor и других "
            "систем мониторинга. В отличие от `/api/v1/metrics`, здесь отдаются не "
            "бизнес-события из read model, а технические runtime-метрики процесса."
        ),
    )
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    return app


app = create_app()

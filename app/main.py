from __future__ import annotations

from app.app_factory import create_service_app
from app.runtime import get_runtime


def create_app():
    # Legacy entrypoint остается агрегирующим API gateway совместимости: он
    # собирает все bounded context-роуты в одном процессе, но теперь использует
    # ту же service factory, что и отдельные микросервисы.
    runtime = get_runtime(
        modules=("registry", "orchestration", "monitoring", "alerting", "audit"),
        service_name="gateway-api",
    )
    settings = runtime.settings
    return create_service_app(
        title="Workflow Operations Platform Gateway",
        description=(
            "Совместимый gateway-режим, собирающий все bounded context-API в одном "
            "процессе. Используется как transitional entrypoint на время миграции "
            "с modular monolith на микросервисную архитектуру."
        ),
        settings=settings,
        runtime=runtime,
        modules=["registry", "orchestration", "monitoring", "alerting", "audit"],
    )


# Экземпляр приложения создается на импорт модуля, потому что именно этот
# объект ожидают uvicorn/gunicorn и тестовая инфраструктура FastAPI.
app = create_app()

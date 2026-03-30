from __future__ import annotations

from fastapi import APIRouter

from app.modules.alerting.api import router as alerting_router
from app.modules.audit.api import router as audit_router
from app.modules.monitoring.api import router as monitoring_router
from app.modules.orchestration.api import router as orchestration_router
from app.modules.registry.api import router as registry_router

ROUTERS = {
    "registry": registry_router,
    "orchestration": orchestration_router,
    "monitoring": monitoring_router,
    "alerting": alerting_router,
    "audit": audit_router,
}


def build_api_router(modules: list[str] | tuple[str, ...] | None = None) -> APIRouter:
    # Этот файл собирает единый HTTP-router из модульных роутеров.
    # Он является тонкой границей между FastAPI-приложением и предметными
    # модулями: main.py знает только про build_api_router(), а детали того,
    # какие именно bounded context публикуют маршруты, скрыты здесь.
    router = APIRouter()

    # Порядок include_router здесь отражает верхнеуровневую структуру API:
    # сначала registry и orchestration как основной прикладной контур,
    # затем monitoring/alerting/audit как эксплуатационный слой.
    # Это не меняет контракт маршрутов, но делает состав API предсказуемым
    # для чтения, сопровождения и будущего выделения модулей в сервисы.
    selected_modules = modules or list(ROUTERS.keys())
    for module_name in selected_modules:
        router.include_router(ROUTERS[module_name])
    return router

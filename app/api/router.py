from __future__ import annotations

from fastapi import APIRouter

from app.modules.alerting.api import router as alerting_router
from app.modules.audit.api import router as audit_router
from app.modules.monitoring.api import router as monitoring_router
from app.modules.orchestration.api import router as orchestration_router
from app.modules.registry.api import router as registry_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(registry_router)
    router.include_router(orchestration_router)
    router.include_router(monitoring_router)
    router.include_router(alerting_router)
    router.include_router(audit_router)
    return router

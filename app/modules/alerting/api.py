from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, require_role
from app.db.session import get_session
from app.domain.schemas import AlertDTO, Page
from app.modules.alerting.queries import AlertQueryService

router = APIRouter(prefix="", tags=["alerting"])


def get_alert_queries() -> AlertQueryService:
    from app.runtime import get_runtime

    return get_runtime().alert_queries


@router.get(
    "/alerts",
    response_model=Page[AlertDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список алертов",
    description=(
        "Возвращает пагинированный список алертов из read model с фильтрацией "
        "по severity и статусу. Ручка нужна операторам для просмотра активных, "
        "подавленных и уже обработанных сигналов платформы."
    ),
)
async def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: AlertQueryService = Depends(get_alert_queries),
) -> Page[AlertDTO]:
    return await service.list_alerts(
        session,
        page=page,
        page_size=page_size,
        severity=severity,
        status=status,
    )

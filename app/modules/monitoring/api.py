from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, require_role
from app.db.session import get_session
from app.domain.schemas import (
    AnomalyReportDTO,
    CostRecordDTO,
    DriftReportDTO,
    MetricSampleDTO,
    Page,
)
from app.modules.monitoring.health import HealthService
from app.modules.monitoring.queries import MonitoringQueryService
from app.modules.monitoring.schemas import HealthSummary, PerformanceSummary

router = APIRouter(prefix="", tags=["monitoring"])


def get_health_service() -> HealthService:
    from app.runtime import get_runtime

    return get_runtime().health_service


def get_monitoring_queries() -> MonitoringQueryService:
    from app.runtime import get_runtime

    return get_runtime().monitoring_queries


@router.get(
    "/metrics",
    response_model=Page[MetricSampleDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
)
async def list_metrics(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    metric_name: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[MetricSampleDTO]:
    return await service.list_metrics(
        session,
        page=page,
        page_size=page_size,
        metric_name=metric_name,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.get(
    "/metrics/summary",
    response_model=PerformanceSummary,
    dependencies=[Depends(require_role(Role.VIEWER))],
)
async def get_metrics_summary(
    window_minutes: int = Query(default=60, ge=5, le=1440),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> PerformanceSummary:
    return await service.performance_summary(session, window_minutes=window_minutes)


@router.get(
    "/costs", response_model=Page[CostRecordDTO], dependencies=[Depends(require_role(Role.VIEWER))]
)
async def list_costs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    environment_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[CostRecordDTO]:
    return await service.list_costs(
        session, page=page, page_size=page_size, environment_id=environment_id
    )


@router.get(
    "/anomalies",
    response_model=Page[AnomalyReportDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
)
async def list_anomalies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[AnomalyReportDTO]:
    return await service.list_anomalies(session, page=page, page_size=page_size, severity=severity)


@router.get(
    "/drift", response_model=Page[DriftReportDTO], dependencies=[Depends(require_role(Role.VIEWER))]
)
async def list_drift(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[DriftReportDTO]:
    return await service.list_drift(session, page=page, page_size=page_size, severity=severity)


@router.get("/health/live", response_model=HealthSummary)
async def live(service: HealthService = Depends(get_health_service)) -> HealthSummary:
    return await service.live()


@router.get("/health/ready", response_model=HealthSummary)
async def ready(
    session: AsyncSession = Depends(get_session),
    service: HealthService = Depends(get_health_service),
) -> HealthSummary:
    return await service.ready(session)


@router.get("/health/deep", response_model=HealthSummary)
async def deep(
    session: AsyncSession = Depends(get_session),
    service: HealthService = Depends(get_health_service),
) -> HealthSummary:
    return await service.deep(session)

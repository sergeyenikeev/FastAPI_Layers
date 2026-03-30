from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
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
from app.runtime_access import get_request_runtime

# Monitoring router отдает только read-side и health-функции платформы.
# Здесь нет прямой логики детекторов или Prometheus runtime-метрик процесса —
# только transport-adapter для monitoring query и health services.
router = APIRouter(prefix="", tags=["monitoring"])


def get_health_service(request: Request) -> HealthService:
    return get_request_runtime(request).health_service


def get_monitoring_queries(request: Request) -> MonitoringQueryService:
    return get_request_runtime(request).monitoring_queries


@router.get(
    "/metrics",
    response_model=Page[MetricSampleDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить сырые метрики из read model",
    description=(
        "Возвращает сохраненные samples бизнес- и системных метрик из PostgreSQL projections. "
        "Ручка нужна для аналитики, аудита и построения внутренних отчетов на уровне платформы."
    ),
)
async def list_metrics(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    metric_name: str | None = Query(default=None, description="Фильтр по имени метрики."),
    entity_type: str | None = Query(
        default=None, description="Фильтр по типу сущности: execution_step, model и т.п."
    ),
    entity_id: str | None = Query(default=None, description="Фильтр по идентификатору сущности."),
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
    summary="Получить агрегированную сводку производительности",
    description=(
        "Возвращает агрегаты по производительности за выбранное окно времени: "
        "latency, throughput, error rate и другие ключевые показатели. "
        "Ручка нужна для быстрых operational dashboard и health-assessment сценариев."
    ),
)
async def get_metrics_summary(
    window_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Окно агрегации в минутах для расчета performance summary.",
    ),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> PerformanceSummary:
    return await service.performance_summary(session, window_minutes=window_minutes)


@router.get(
    "/costs",
    response_model=Page[CostRecordDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить записи о стоимости выполнения",
    description=(
        "Возвращает cost records из read model с возможностью фильтрации по окружению. "
        "Ручка нужна для контроля расходов и разбора стоимости по execution-средам."
    ),
)
async def list_costs(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    environment_id: str | None = Query(
        default=None, description="Фильтр по окружению, например dev, stage или prod."
    ),
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
    summary="Получить отчеты по аномалиям",
    description=(
        "Возвращает anomaly reports, сформированные детекторами на основе метрик и событий. "
        "Ручка нужна для просмотра подозрительных всплесков latency, ошибок, стоимости, "
        "token usage и других отклонений."
    ),
)
async def list_anomalies(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    severity: str | None = Query(
        default=None, description="Фильтр по severity: info, warning, critical."
    ),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[AnomalyReportDTO]:
    return await service.list_anomalies(session, page=page, page_size=page_size, severity=severity)


@router.get(
    "/drift",
    response_model=Page[DriftReportDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить отчеты по дрейфу",
    description=(
        "Возвращает drift reports по данным, выходам и embedding-представлениям. "
        "Ручка нужна для контроля деградации поведения и стабильности результатов модели."
    ),
)
async def list_drift(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    severity: str | None = Query(
        default=None, description="Фильтр по severity: info, warning, critical."
    ),
    session: AsyncSession = Depends(get_session),
    service: MonitoringQueryService = Depends(get_monitoring_queries),
) -> Page[DriftReportDTO]:
    return await service.list_drift(session, page=page, page_size=page_size, severity=severity)


@router.get(
    "/health/live",
    response_model=HealthSummary,
    summary="Проверка liveness",
    description=(
        "Самая легкая health-проверка процесса. "
        "Нужна kubelet и внешним системам, чтобы понять, жив ли HTTP-процесс вообще. "
        "Эта ручка не проверяет глубоко внешние зависимости."
    ),
)
async def live(service: HealthService = Depends(get_health_service)) -> HealthSummary:
    return await service.live()


@router.get(
    "/health/ready",
    response_model=HealthSummary,
    summary="Проверка readiness",
    description=(
        "Проверяет, готово ли приложение обслуживать пользовательские запросы. "
        "Обычно используется readiness probe и учитывает доступность обязательных "
        "зависимостей, нужных для нормальной работы API."
    ),
)
async def ready(
    session: AsyncSession = Depends(get_session),
    service: HealthService = Depends(get_health_service),
) -> HealthSummary:
    return await service.ready(session)


@router.get(
    "/health/deep",
    response_model=HealthSummary,
    summary="Глубокая проверка зависимостей",
    description=(
        "Проверяет расширенный набор зависимостей: базу данных, Redis, Kafka, "
        "model endpoint-ы и состояние worker-контуров. Ручка нужна для операционной "
        "диагностики и runbook-сценариев, когда простой readiness уже недостаточен."
    ),
)
async def deep(
    session: AsyncSession = Depends(get_session),
    service: HealthService = Depends(get_health_service),
) -> HealthSummary:
    return await service.deep(session)

from __future__ import annotations

from datetime import timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.db.models import AnomalyReport, CostRecord, DriftReport, ExecutionRun, MetricSample
from app.db.repositories import paginate_query
from app.domain.enums import ExecutionStatus
from app.domain.schemas import (
    AnomalyReportDTO,
    CostRecordDTO,
    DriftReportDTO,
    MetricSampleDTO,
    Page,
)
from app.modules.monitoring.schemas import PerformanceSummary


def percentile(values: list[float], q: float) -> float:
    # Локальная реализация percentile keeps monitoring query service независимым
    # от внешних научных библиотек и полностью детерминированным в тестах.
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


class MonitoringQueryService:
    # MonitoringQueryService работает только по read-side таблицам метрик, стоимости,
    # anomaly и drift. Он не читает Prometheus напрямую и не ходит в Kafka.
    async def list_metrics(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        metric_name: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> Page[MetricSampleDTO]:
        query = select(MetricSample).order_by(MetricSample.sampled_at.desc())
        if metric_name:
            query = query.where(MetricSample.metric_name == metric_name)
        if entity_type:
            query = query.where(MetricSample.entity_type == entity_type)
        if entity_id:
            query = query.where(MetricSample.entity_id == entity_id)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[MetricSampleDTO](
            items=[MetricSampleDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def performance_summary(
        self, session: AsyncSession, window_minutes: int = 60
    ) -> PerformanceSummary:
        # Summary собирает агрегаты из materialized metric history и execution history,
        # а не из runtime counters. Это делает ответ воспроизводимым и историчным.
        window_start = utc_now() - timedelta(minutes=window_minutes)
        latency_query = select(MetricSample.value).where(
            MetricSample.metric_name == "step_duration_ms",
            MetricSample.sampled_at >= window_start,
        )
        token_query = select(func.sum(MetricSample.value)).where(
            MetricSample.metric_name == "step_token_usage",
            MetricSample.sampled_at >= window_start,
        )
        lag_query = select(func.avg(MetricSample.value)).where(
            MetricSample.metric_name == "consumer_lag",
            MetricSample.sampled_at >= window_start,
        )
        execution_total_query = (
            select(func.count())
            .select_from(ExecutionRun)
            .where(ExecutionRun.started_at >= window_start)
        )
        execution_failed_query = (
            select(func.count())
            .select_from(ExecutionRun)
            .where(
                ExecutionRun.started_at >= window_start,
                ExecutionRun.status == ExecutionStatus.FAILED,
            )
        )

        latency_values = [
            float(value) for value in (await session.execute(latency_query)).scalars().all()
        ]
        token_usage_total = float((await session.execute(token_query)).scalar() or 0.0)
        consumer_lag = float((await session.execute(lag_query)).scalar() or 0.0)
        execution_total = int((await session.execute(execution_total_query)).scalar() or 0)
        execution_failed = int((await session.execute(execution_failed_query)).scalar() or 0)
        throughput = execution_total / max(window_minutes, 1)
        error_rate = execution_failed / execution_total if execution_total else 0.0

        return PerformanceSummary(
            latency_p50_ms=percentile(latency_values, 0.50),
            latency_p95_ms=percentile(latency_values, 0.95),
            latency_p99_ms=percentile(latency_values, 0.99),
            throughput_per_minute=throughput,
            error_rate=error_rate,
            token_usage_total=token_usage_total,
            consumer_lag=consumer_lag,
            step_duration_avg_ms=mean(latency_values) if latency_values else 0.0,
        )

    async def list_costs(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        environment_id: str | None = None,
    ) -> Page[CostRecordDTO]:
        query = select(CostRecord).order_by(CostRecord.occurred_at.desc())
        if environment_id:
            query = query.where(CostRecord.environment_id == environment_id)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[CostRecordDTO](
            items=[CostRecordDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_anomalies(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        severity: str | None = None,
    ) -> Page[AnomalyReportDTO]:
        query = select(AnomalyReport).order_by(AnomalyReport.detected_at.desc())
        if severity:
            query = query.where(AnomalyReport.severity == severity)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[AnomalyReportDTO](
            items=[AnomalyReportDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_drift(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        severity: str | None = None,
    ) -> Page[DriftReportDTO]:
        query = select(DriftReport).order_by(DriftReport.detected_at.desc())
        if severity:
            query = query.where(DriftReport.severity == severity)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[DriftReportDTO](
            items=[DriftReportDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

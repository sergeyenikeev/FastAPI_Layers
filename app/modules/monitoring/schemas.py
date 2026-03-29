from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    component: str = Field(description="Имя проверяемого компонента.")
    status: str = Field(description="Состояние компонента: passing, degraded или failing.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Расширенные детали проверки компонента."
    )
    checked_at: datetime = Field(description="Время выполнения проверки.")


class HealthSummary(BaseModel):
    status: str = Field(description="Итоговый статус health-проверки.")
    components: list[ComponentHealth] = Field(
        description="Список статусов по отдельным инфраструктурным и runtime-компонентам."
    )


class PerformanceSummary(BaseModel):
    latency_p50_ms: float = Field(description="Латентность p50 в миллисекундах.")
    latency_p95_ms: float = Field(description="Латентность p95 в миллисекундах.")
    latency_p99_ms: float = Field(description="Латентность p99 в миллисекундах.")
    throughput_per_minute: float = Field(description="Количество операций в минуту.")
    error_rate: float = Field(description="Доля ошибок в выбранном окне.")
    token_usage_total: float = Field(description="Суммарное использование токенов.")
    consumer_lag: float = Field(description="Суммарный lag Kafka consumers.")
    step_duration_avg_ms: float = Field(description="Средняя длительность шага выполнения.")


class TimeSeriesAggregate(BaseModel):
    bucket: str
    value: float

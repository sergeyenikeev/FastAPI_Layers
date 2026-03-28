from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    component: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime


class HealthSummary(BaseModel):
    status: str
    components: list[ComponentHealth]


class PerformanceSummary(BaseModel):
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_per_minute: float
    error_rate: float
    token_usage_total: float
    consumer_lag: float
    step_duration_avg_ms: float


class TimeSeriesAggregate(BaseModel):
    bucket: str
    value: float

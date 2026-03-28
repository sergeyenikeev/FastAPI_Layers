from __future__ import annotations

from enum import StrEnum


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    FAILED = "failed"


class DeploymentStatus(StrEnum):
    PENDING = "pending"
    DEPLOYED = "deployed"
    FAILED = "failed"
    PAUSED = "paused"
    ROLLING_OUT = "rolling_out"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HealthStatus(StrEnum):
    PASSING = "passing"
    DEGRADED = "degraded"
    FAILING = "failing"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class AnomalyType(StrEnum):
    LATENCY_SPIKE = "latency_spike"
    ERROR_SPIKE = "error_spike"
    COST_SPIKE = "cost_spike"
    EXECUTION_DROP = "execution_drop"
    TOKEN_ANOMALY = "token_anomaly"


class DriftType(StrEnum):
    DATA_DRIFT = "data_drift"
    OUTPUT_DRIFT = "output_drift"
    EMBEDDING_DRIFT = "embedding_drift"


class ReportStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    RESOLVED = "resolved"

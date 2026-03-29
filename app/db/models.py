from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.domain.enums import (
    AlertSeverity,
    AlertStatus,
    AnomalyType,
    DeploymentStatus,
    DriftType,
    ExecutionStatus,
    HealthStatus,
    LifecycleStatus,
    ReportStatus,
)


# Этот модуль описывает materialized state платформы в PostgreSQL.
# Здесь живут и registry-сущности, и execution read-side, и operational таблицы
# вроде metrics/anomalies/alerts/audit/processed_events.
class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # Agent — верхнеуровневая registry-сущность. Исполнимым его делает не сам
    # объект, а одна из связанных AgentVersion, где хранится runtime-конфигурация.
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    owner: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default=LifecycleStatus.ACTIVE)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    versions: Mapped[list[AgentVersion]] = relationship(back_populates="agent")


class GraphDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # GraphDefinition описывает логический workflow отдельно от конкретного агента.
    __tablename__ = "graph_definitions"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    version: Mapped[str] = mapped_column(String(50))
    entrypoint: Mapped[str] = mapped_column(String(255))
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    agent_versions: Mapped[list[AgentVersion]] = relationship(back_populates="graph_definition")
    execution_runs: Mapped[list[ExecutionRun]] = relationship(back_populates="graph_definition")


class AgentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # Version отделена от Agent, чтобы один logical agent мог эволюционировать
    # без потери истории и чтобы deployment ссылался на стабильную версию.
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_version"),)

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    graph_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("graph_definitions.id", ondelete="SET NULL"),
        index=True,
    )
    version: Mapped[str] = mapped_column(String(50))
    runtime_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    agent: Mapped[Agent] = relationship(back_populates="versions")
    graph_definition: Mapped[GraphDefinition] = relationship(back_populates="agent_versions")
    deployments: Mapped[list[Deployment]] = relationship(back_populates="agent_version")


class ModelEndpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # ModelEndpoint хранит конфигурацию точки входа к inference-провайдеру.
    __tablename__ = "model_endpoints"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(500))
    auth_type: Mapped[str] = mapped_column(String(50), default="bearer")
    status: Mapped[str] = mapped_column(String(50), default=LifecycleStatus.ACTIVE)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    versions: Mapped[list[ModelVersion]] = relationship(back_populates="model_endpoint")


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # ModelVersion фиксирует конкретную версию модели, tokenizer и pricing.
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_endpoint_id", "version", name="uq_model_version"),)

    model_endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("model_endpoints.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(255))
    tokenizer_name: Mapped[str | None] = mapped_column(String(255))
    context_window: Mapped[int | None] = mapped_column(Integer)
    pricing: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    model_endpoint: Mapped[ModelEndpoint] = relationship(back_populates="versions")
    deployments: Mapped[list[Deployment]] = relationship(back_populates="model_version")


class ToolDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_definitions"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    implementation_path: Mapped[str] = mapped_column(String(500))


class Environment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "environments"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    deployments: Mapped[list[Deployment]] = relationship(back_populates="environment")


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # Deployment связывает agent version, model version и environment в одну
    # исполнимую конфигурацию, по которой потом стартуют execution run-ы.
    __tablename__ = "deployments"

    agent_version_id: Mapped[str] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    environment_id: Mapped[str] = mapped_column(
        ForeignKey("environments.id", ondelete="RESTRICT"),
        index=True,
    )
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default=DeploymentStatus.PENDING)
    replica_count: Mapped[int] = mapped_column(Integer, default=1)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    agent_version: Mapped[AgentVersion] = relationship(back_populates="deployments")
    environment: Mapped[Environment] = relationship(back_populates="deployments")
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="deployments")
    execution_runs: Mapped[list[ExecutionRun]] = relationship(back_populates="deployment")


class ExecutionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # ExecutionRun — read-side запись о запуске сценария. Она обновляется
    # событиями execution.started / execution.finished / execution.failed.
    __tablename__ = "execution_runs"

    deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"),
        index=True,
    )
    graph_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("graph_definitions.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default=ExecutionStatus.PENDING)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    error_message: Mapped[str | None] = mapped_column(Text())

    deployment: Mapped[Deployment | None] = relationship(back_populates="execution_runs")
    graph_definition: Mapped[GraphDefinition | None] = relationship(back_populates="execution_runs")
    steps: Mapped[list[ExecutionStep]] = relationship(back_populates="execution_run")


class ExecutionStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # ExecutionStep materializes step-level telemetry и бизнес-результат каждого
    # узла workflow, что делает разбор execution-а детальным и аудируемым.
    __tablename__ = "execution_steps"

    execution_run_id: Mapped[str] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    step_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), default=ExecutionStatus.PENDING)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    token_usage_total: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str] = mapped_column(String(64), index=True)

    execution_run: Mapped[ExecutionRun] = relationship(back_populates="steps")


class HealthCheckResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "health_check_results"

    component: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), default=HealthStatus.PASSING)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    environment_id: Mapped[str | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL")
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class MetricSample(UUIDPrimaryKeyMixin, Base):
    # MetricSample — историческая read model для system/business metrics, которую
    # используют monitoring query endpoints, anomaly detection и drift logic.
    __tablename__ = "metric_samples"
    __table_args__ = (
        Index("ix_metric_samples_metric_name_sampled_at", "metric_name", "sampled_at"),
    )

    metric_name: Mapped[str] = mapped_column(String(255), index=True)
    metric_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    value: Mapped[float] = mapped_column(Float)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CostRecord(UUIDPrimaryKeyMixin, Base):
    # CostRecord отделен от ExecutionRun, потому что один run может порождать
    # несколько cost events и cost analytics требуют своей временной истории.
    __tablename__ = "cost_records"
    __table_args__ = (Index("ix_cost_records_occurred_at", "occurred_at"),)

    execution_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="SET NULL"),
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(String(36), index=True)
    environment_id: Mapped[str | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"),
        index=True,
    )
    usd_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnomalyReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "anomaly_reports"
    __table_args__ = (Index("ix_anomaly_reports_detected_at", "detected_at"),)

    anomaly_type: Mapped[str] = mapped_column(String(100), default=AnomalyType.LATENCY_SPIKE)
    severity: Mapped[str] = mapped_column(String(50), default=AlertSeverity.WARNING)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    score: Mapped[float] = mapped_column(Float)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    observed_value: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(50), default=ReportStatus.OPEN)


class DriftReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "drift_reports"
    __table_args__ = (Index("ix_drift_reports_detected_at", "detected_at"),)

    drift_type: Mapped[str] = mapped_column(String(100), default=DriftType.DATA_DRIFT)
    severity: Mapped[str] = mapped_column(String(50), default=AlertSeverity.WARNING)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    metric_name: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(50), default=ReportStatus.OPEN)


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    # Alert — materialized operational сигнал после dedupe и cooldown политики.
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_alert_dedupe_key"),)

    severity: Mapped[str] = mapped_column(String(50), default=AlertSeverity.INFO)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(50), default=AlertStatus.OPEN)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)

    actor: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(255), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProcessedEvent(UUIDPrimaryKeyMixin, Base):
    # ProcessedEvent — основа consumer idempotency. Таблица хранит, что именно
    # уже было успешно обработано конкретной consumer group.
    __tablename__ = "processed_events"
    __table_args__ = (
        UniqueConstraint("consumer_group", "event_id", name="uq_processed_event_consumer_group"),
    )

    consumer_group: Mapped[str] = mapped_column(String(255), index=True)
    event_id: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(String(255))
    partition: Mapped[int] = mapped_column(Integer)
    offset: Mapped[int] = mapped_column(Integer)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkerHeartbeat(UUIDPrimaryKeyMixin, Base):
    # Heartbeat read model показывает, какие worker-процессы живы и когда
    # последний раз подтверждали свое присутствие в event backbone.
    __tablename__ = "worker_heartbeats"
    __table_args__ = (UniqueConstraint("worker_name", name="uq_worker_heartbeat_worker_name"),)

    worker_name: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(255))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str | None = None


class Page[T](APIModel):
    items: list[T] = Field(description="Элементы текущей страницы.")
    total: int = Field(description="Общее число элементов по запросу.")
    page: int = Field(description="Номер текущей страницы.")
    page_size: int = Field(description="Размер страницы.")


class CommandAccepted(APIModel):
    entity_id: str = Field(description="Идентификатор сущности, для которой принята команда.")
    event_id: str = Field(description="Идентификатор опубликованного доменного события.")
    event_type: str = Field(description="Тип опубликованного события.")
    status: str = Field(default="accepted", description="Статус приема команды API.")
    correlation_id: str = Field(
        description="Correlation ID для трассировки команды через систему."
    )


class AgentDTO(APIModel):
    id: str
    name: str
    description: str | None = None
    owner: str | None = None
    status: str
    tags: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AgentVersionDTO(APIModel):
    id: str
    agent_id: str
    graph_definition_id: str | None = None
    version: str
    runtime_config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GraphDefinitionDTO(APIModel):
    id: str
    name: str
    description: str | None = None
    version: str
    entrypoint: str
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ModelEndpointDTO(APIModel):
    id: str
    name: str
    provider: str
    base_url: str
    auth_type: str
    status: str
    capabilities: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ModelVersionDTO(APIModel):
    id: str
    model_endpoint_id: str
    version: str
    model_name: str
    tokenizer_name: str | None = None
    context_window: int | None = None
    pricing: dict[str, Any]
    is_default: bool
    created_at: datetime
    updated_at: datetime


class DeploymentDTO(APIModel):
    id: str
    agent_version_id: str
    environment_id: str
    model_version_id: str | None = None
    status: str
    replica_count: int
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ToolDefinitionDTO(APIModel):
    id: str
    name: str
    description: str | None = None
    schema_definition: dict[str, Any] = Field(
        validation_alias=AliasChoices("schema_json", "schema_definition"),
        serialization_alias="schema_json",
    )
    implementation_path: str
    created_at: datetime
    updated_at: datetime


class EnvironmentDTO(APIModel):
    id: str
    name: str
    description: str | None = None
    labels: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ExecutionStepDTO(APIModel):
    id: str = Field(description="Идентификатор шага выполнения.")
    execution_run_id: str = Field(description="Идентификатор родительского execution run.")
    agent_name: str = Field(description="Имя агента, выполнившего шаг.")
    step_name: str = Field(description="Логическое имя шага в workflow.")
    status: str = Field(description="Статус шага выполнения.")
    input_payload: dict[str, Any] = Field(description="Входные данные шага.")
    output_payload: dict[str, Any] | None = Field(
        default=None, description="Результат шага после выполнения."
    )
    duration_ms: float | None = Field(
        default=None, description="Длительность шага в миллисекундах."
    )
    token_usage_total: int = Field(description="Суммарный расход токенов на шаге.")
    started_at: datetime = Field(description="Время начала шага.")
    finished_at: datetime | None = Field(default=None, description="Время завершения шага.")
    trace_id: str = Field(description="Trace ID, связанный с шагом.")
    created_at: datetime = Field(description="Время создания записи в read model.")
    updated_at: datetime = Field(description="Время последнего обновления записи.")


class ExecutionRunDTO(APIModel):
    id: str = Field(description="Идентификатор запуска выполнения.")
    deployment_id: str | None = None
    graph_definition_id: str | None = None
    status: str = Field(description="Статус выполнения: running, succeeded или failed.")
    input_payload: dict[str, Any] = Field(description="Исходный входной payload выполнения.")
    output_payload: dict[str, Any] | None = Field(
        default=None, description="Итоговый payload результата выполнения."
    )
    started_at: datetime = Field(description="Время старта выполнения.")
    finished_at: datetime | None = Field(default=None, description="Время завершения выполнения.")
    correlation_id: str = Field(description="Correlation ID выполнения.")
    trace_id: str = Field(description="Trace ID выполнения.")
    error_message: str | None = Field(
        default=None,
        description="Текст ошибки, если выполнение завершилось неуспешно.",
    )
    created_at: datetime = Field(description="Время создания записи в read model.")
    updated_at: datetime = Field(description="Время последнего обновления записи.")
    steps: list[ExecutionStepDTO] = Field(
        default_factory=list,
        description="Материализованный список шагов выполнения в порядке их обработки.",
    )


class HealthCheckDTO(APIModel):
    id: str
    component: str
    status: str
    details: dict[str, Any]
    environment_id: str | None = None
    checked_at: datetime


class MetricSampleDTO(APIModel):
    id: str
    metric_name: str
    metric_type: str
    entity_type: str
    entity_id: str
    value: float
    tags: dict[str, Any]
    sampled_at: datetime


class CostRecordDTO(APIModel):
    id: str
    execution_run_id: str | None = None
    agent_id: str | None = None
    workflow_id: str | None = None
    environment_id: str | None = None
    usd_cost: float
    token_input: int
    token_output: int
    provider: str | None = None
    model_name: str | None = None
    occurred_at: datetime


class AnomalyReportDTO(APIModel):
    id: str
    anomaly_type: str
    severity: str
    entity_type: str
    entity_id: str
    score: float
    baseline_value: float | None = None
    observed_value: float | None = None
    metadata: dict[str, Any] = Field(validation_alias=AliasChoices("metadata", "metadata_json"))
    detected_at: datetime
    status: str


class DriftReportDTO(APIModel):
    id: str
    drift_type: str
    severity: str
    entity_type: str
    entity_id: str
    metric_name: str
    score: float
    threshold: float
    metadata: dict[str, Any] = Field(validation_alias=AliasChoices("metadata", "metadata_json"))
    detected_at: datetime
    status: str


class AlertDTO(APIModel):
    id: str
    severity: str
    dedupe_key: str
    source_event_id: str | None = None
    title: str
    description: str
    status: str
    last_sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventDTO(APIModel):
    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    correlation_id: str
    trace_id: str
    payload: dict[str, Any]
    created_at: datetime

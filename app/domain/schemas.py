from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str | None = None


class Page(APIModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class CommandAccepted(APIModel):
    entity_id: str
    event_id: str
    event_type: str
    status: str = "accepted"
    correlation_id: str


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
    id: str
    execution_run_id: str
    agent_name: str
    step_name: str
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    duration_ms: float | None = None
    token_usage_total: int
    started_at: datetime
    finished_at: datetime | None = None
    trace_id: str
    created_at: datetime
    updated_at: datetime


class ExecutionRunDTO(APIModel):
    id: str
    deployment_id: str | None = None
    graph_definition_id: str | None = None
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None
    correlation_id: str
    trace_id: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[ExecutionStepDTO] = Field(default_factory=list)


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

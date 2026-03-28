from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    name: str
    description: str | None = None
    owner: str | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    version: str = "v1"
    graph_definition_id: str | None = None
    runtime_config: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentRequest(BaseModel):
    description: str | None = None
    owner: str | None = None
    status: str | None = None
    tags: dict[str, Any] | None = None


class CreateModelRequest(BaseModel):
    name: str
    provider: str
    base_url: str
    auth_type: str = "bearer"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    version: str = "v1"
    model_name: str
    tokenizer_name: str | None = None
    context_window: int | None = None
    pricing: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = True


class UpdateModelRequest(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    auth_type: str | None = None
    status: str | None = None
    capabilities: dict[str, Any] | None = None


class CreateGraphRequest(BaseModel):
    name: str
    description: str | None = None
    version: str = "v1"
    entrypoint: str = "planner"
    definition: dict[str, Any] = Field(default_factory=dict)


class UpdateGraphRequest(BaseModel):
    description: str | None = None
    version: str | None = None
    entrypoint: str | None = None
    definition: dict[str, Any] | None = None


class CreateDeploymentRequest(BaseModel):
    agent_version_id: str
    model_version_id: str | None = None
    environment_id: str | None = None
    environment_name: str = "dev"
    environment_description: str | None = None
    replica_count: int = Field(default=1, ge=1)
    configuration: dict[str, Any] = Field(default_factory=dict)


class UpdateDeploymentRequest(BaseModel):
    status: str | None = None
    replica_count: int | None = Field(default=None, ge=1)
    configuration: dict[str, Any] | None = None


class CreateToolRequest(BaseModel):
    name: str
    description: str | None = None
    schema_definition: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="schema_json",
        serialization_alias="schema_json",
    )
    implementation_path: str


class UpdateToolRequest(BaseModel):
    description: str | None = None
    schema_definition: dict[str, Any] | None = Field(
        default=None,
        validation_alias="schema_json",
        serialization_alias="schema_json",
    )
    implementation_path: str | None = None


class CreateEnvironmentRequest(BaseModel):
    name: str
    description: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)


class UpdateEnvironmentRequest(BaseModel):
    description: str | None = None
    labels: dict[str, Any] | None = None

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateExecutionRequest(BaseModel):
    deployment_id: str | None = None
    graph_definition_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelInvocationResult(BaseModel):
    content: str
    latency_ms: float
    token_input: int
    token_output: int
    cost_usd: float
    model_name: str
    provider: str

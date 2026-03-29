from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    # EventEnvelope — единый wire contract для всех событий платформы.
    # И command-side, и workers, и projections работают только с этим форматом.
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_version: str = "1.0"
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str
    trace_id: str
    source: str
    entity_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeadLetterEnvelope(BaseModel):
    # DLQ envelope сохраняет исходное событие нетронутым и добавляет только
    # operational metadata о consumer group, retry count и причине сбоя.
    topic: str
    consumer_group: str
    retry_count: int
    error: str
    original_event: EventEnvelope

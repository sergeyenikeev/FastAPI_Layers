from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import EventEnvelope
from app.messaging.kafka import (
    BaseConsumerWorker,
    EventHandler,
    InMemoryPublisher,
    deserialize_event,
    serialize_event,
)
from app.runtime import AppRuntime


@dataclass
class FakeRecord:
    topic: str
    partition: int
    offset: int
    value: bytes


@pytest.mark.kafka
def test_event_roundtrip_serialization() -> None:
    event = EventEnvelope(
        event_type="agent.created",
        correlation_id="corr-1",
        trace_id="trace-1",
        source="test",
        entity_id="entity-1",
        payload={"foo": "bar"},
    )
    assert deserialize_event(serialize_event(event)) == event


@pytest.mark.kafka
@pytest.mark.asyncio
async def test_consumer_idempotency(runtime: AppRuntime) -> None:
    handled: list[str] = []

    async def handler(event: EventEnvelope, _record: Any, _session: AsyncSession) -> None:
        handled.append(event.event_id)

    worker = BaseConsumerWorker(
        name="test-consumer",
        group_id="test-group",
        topics=["registry.events"],
        handler=cast(EventHandler, handler),
        session_factory=runtime.session_factory,
        publisher=runtime.publisher,
        settings=runtime.settings,
    )

    async def fake_commit(_record: Any) -> None:
        return None

    worker._commit = fake_commit  # type: ignore[assignment]
    event = EventEnvelope(
        event_type="agent.created",
        correlation_id="corr-1",
        trace_id="trace-1",
        source="test",
        entity_id="entity-1",
        payload={"foo": "bar"},
    )
    record = FakeRecord(
        topic="registry.events", partition=0, offset=1, value=serialize_event(event)
    )

    await worker._process_record(record)
    await worker._process_record(record)
    assert handled == [event.event_id]


@pytest.mark.kafka
@pytest.mark.asyncio
async def test_consumer_sends_event_to_dlq_after_retries(runtime: AppRuntime) -> None:
    publisher = cast(InMemoryPublisher, runtime.publisher)

    async def failing_handler(
        _event: EventEnvelope, _record: Any, _session: AsyncSession
    ) -> None:
        raise RuntimeError("boom")

    worker = BaseConsumerWorker(
        name="failing-consumer",
        group_id="failing-group",
        topics=["system.metrics"],
        handler=cast(EventHandler, failing_handler),
        session_factory=runtime.session_factory,
        publisher=runtime.publisher,
        settings=runtime.settings,
        max_retries=2,
    )

    async def fake_commit(_record: Any) -> None:
        return None

    worker._commit = fake_commit  # type: ignore[assignment]
    event = EventEnvelope(
        event_type="metric.recorded",
        correlation_id="corr-1",
        trace_id="trace-1",
        source="test",
        entity_id="metric-1",
        payload={"metric_name": "latency", "value": 42},
    )
    record = FakeRecord(topic="system.metrics", partition=0, offset=1, value=serialize_event(event))

    await worker._process_record(record)
    topics = [topic for topic, _event in publisher.events]
    assert "system.metrics.dlq" in topics

from __future__ import annotations

import asyncio
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
from app.modules.orchestration.schemas import CreateExecutionRequest
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


@pytest.mark.kafka
@pytest.mark.asyncio
async def test_langgraph_execution_publishes_expected_kafka_event_sequence(
    runtime: AppRuntime,
) -> None:
    publisher = cast(InMemoryPublisher, runtime.publisher)

    async with runtime.session_factory() as session:
        response = await runtime.execution_commands.create_execution(
            session,
            CreateExecutionRequest(
                graph_definition_id="graph-kafka-sequence",
                input_payload={"objective": "Verify workflow event sequence"},
            ),
        )

    await asyncio.sleep(0.05)

    execution_events = [
        event
        for topic, event in publisher.events
        if topic in {"agent.executions", "agent.steps", "system.metrics", "cost.events"}
    ]

    assert response.event_type == "execution.started"
    assert any(event.event_type == "execution.started" for event in execution_events)
    assert any(event.event_type == "execution.finished" for event in execution_events)

    step_events = [
        event for topic, event in publisher.events if topic == "agent.steps"
    ]
    assert [event.payload["execution_step"]["step_name"] for event in step_events] == [
        "planner",
        "tool_runner",
        "reviewer",
    ]

    metric_events = [
        event
        for topic, event in publisher.events
        if topic == "system.metrics" and event.event_type == "metric.recorded"
    ]
    metric_names = {event.payload["metric_name"] for event in metric_events}
    assert "step_duration_ms" in metric_names
    assert "step_token_usage" in metric_names

    cost_events = [event for topic, event in publisher.events if topic == "cost.events"]
    assert len(cost_events) >= 1


@pytest.mark.kafka
@pytest.mark.asyncio
async def test_langgraph_execution_publishes_validator_branch_events(
    runtime: AppRuntime,
) -> None:
    publisher = cast(InMemoryPublisher, runtime.publisher)

    async with runtime.session_factory() as session:
        response = await runtime.execution_commands.create_execution(
            session,
            CreateExecutionRequest(
                graph_definition_id="graph-kafka-validator-branch",
                input_payload={
                    "objective": "Verify validator branch event sequence",
                    "require_validation": True,
                },
            ),
        )

    await asyncio.sleep(0.05)

    execution_events = [
        event
        for topic, event in publisher.events
        if topic in {"agent.executions", "agent.steps", "system.metrics", "cost.events"}
    ]

    assert response.event_type == "execution.started"
    assert any(event.event_type == "execution.finished" for event in execution_events)

    step_events = [event for topic, event in publisher.events if topic == "agent.steps"]
    assert [event.payload["execution_step"]["step_name"] for event in step_events] == [
        "planner",
        "tool_runner",
        "validator",
        "reviewer",
    ]

    validator_event = next(
        event
        for event in step_events
        if event.payload["execution_step"]["step_name"] == "validator"
    )
    assert validator_event.payload["execution_step"]["agent_name"] == "validator-agent"

    metric_events = [
        event
        for topic, event in publisher.events
        if topic == "system.metrics" and event.event_type == "metric.recorded"
    ]
    metric_names = {event.payload["metric_name"] for event in metric_events}
    assert "step_duration_ms" in metric_names
    assert "step_token_usage" in metric_names

from __future__ import annotations

from typing import cast

import pytest

from app.domain.events import EventEnvelope
from app.messaging.kafka import InMemoryPublisher
from app.modules.alerting.service import AlertingService
from app.runtime import AppRuntime
from app.workers import AlertHandler


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alert_handler_creates_alert_event_and_projection(runtime: AppRuntime) -> None:
    # Сквозной тест на alerting flow: anomaly signal -> alert event -> projection -> read query.
    publisher = cast(InMemoryPublisher, runtime.publisher)
    event = EventEnvelope(
        event_type="anomaly.detected",
        correlation_id="corr-1",
        trace_id="trace-1",
        source="test",
        entity_id="anomaly-1",
        payload={
            "anomaly_report": {
                "id": "anomaly-1",
                "anomaly_type": "latency_spike",
                "severity": "warning",
                "entity_type": "execution",
                "entity_id": "exec-1",
                "score": 2.1,
                "baseline_value": 100.0,
                "observed_value": 250.0,
                "metadata": {"reason": "zscore_exceeded"},
                "detected_at": "2026-01-01T00:00:00+00:00",
                "status": "open",
            }
        },
    )
    handler = AlertHandler(AlertingService(runtime.publisher, runtime.settings))

    async with runtime.session_factory() as session:
        await handler(event, None, session)
        await session.commit()

    async with runtime.session_factory() as session:
        for _topic, emitted_event in publisher.events:
            await runtime.projector.apply(session, emitted_event)
        await session.commit()

    async with runtime.session_factory() as session:
        alerts = await runtime.alert_queries.list_alerts(session, page=1, page_size=10)
    assert alerts.total == 1
    assert alerts.items[0].title.startswith("Anomaly detected")

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.context import get_correlation_id, get_trace_id
from app.core.logging import get_logger
from app.db.base import utc_now
from app.db.models import CostRecord, MetricSample
from app.domain.events import EventEnvelope
from app.messaging.kafka import BaseConsumerWorker, EventHandler, PublisherProtocol
from app.messaging.topics import (
    AGENT_EXECUTIONS_TOPIC,
    AGENT_STEPS_TOPIC,
    ALERTS_EVENTS_TOPIC,
    ANOMALY_EVENTS_TOPIC,
    AUDIT_EVENTS_TOPIC,
    COST_EVENTS_TOPIC,
    DRIFT_EVENTS_TOPIC,
    MODEL_INFERENCE_TOPIC,
    REGISTRY_EVENTS_TOPIC,
    SYSTEM_HEALTH_TOPIC,
    SYSTEM_METRICS_TOPIC,
)
from app.modules.alerting.service import AlertingService
from app.modules.monitoring.anomaly import AnomalyDetectionService
from app.modules.monitoring.drift import DriftDetectionService
from app.projections.projector import ProjectionService

logger = get_logger(__name__)


class ProjectionHandler:
    def __init__(self, projector: ProjectionService) -> None:
        self.projector = projector

    async def __call__(
        self, event: EventEnvelope, _record: Any, session: AsyncSession
    ) -> None:
        await self.projector.apply(session, event)


class MetricsAggregationHandler:
    def __init__(self, publisher: PublisherProtocol) -> None:
        self.publisher = publisher

    async def __call__(
        self, event: EventEnvelope, _record: Any, _session: AsyncSession
    ) -> None:
        if event.event_type == "execution.started":
            await self._publish_metric("execution_started", event.entity_id, 1.0)
        elif event.event_type == "execution.finished":
            await self._publish_metric("execution_finished", event.entity_id, 1.0)
        elif event.event_type == "execution.failed":
            await self._publish_metric("execution_failed", event.entity_id, 1.0)

    async def _publish_metric(self, metric_name: str, entity_id: str, value: float) -> None:
        await self.publisher.publish(
            SYSTEM_METRICS_TOPIC,
            EventEnvelope(
                event_type="metric.recorded",
                correlation_id=get_correlation_id(),
                trace_id=get_trace_id(),
                source="worker.metrics",
                entity_id=entity_id,
                payload={
                    "metric_name": metric_name,
                    "metric_type": "counter",
                    "entity_type": "execution",
                    "entity_id": entity_id,
                    "value": value,
                    "tags": {"source": "metrics-aggregation-worker"},
                    "sampled_at": utc_now(),
                },
                metadata={"aggregate": "metric"},
            ),
        )


class AnomalyHandler:
    def __init__(
        self, publisher: PublisherProtocol, detection_service: AnomalyDetectionService
    ) -> None:
        self.publisher = publisher
        self.detection_service = detection_service

    async def __call__(
        self, event: EventEnvelope, _record: Any, session: AsyncSession
    ) -> None:
        if event.event_type == "metric.recorded":
            await self._handle_metric_event(event, session)
        elif event.event_type == "cost.recorded":
            await self._handle_cost_event(event, session)

    async def _handle_metric_event(self, event: EventEnvelope, session: AsyncSession) -> None:
        payload = event.payload
        history_query = (
            select(MetricSample.value)
            .where(
                MetricSample.metric_name == payload["metric_name"],
                MetricSample.entity_id == payload["entity_id"],
            )
            .order_by(desc(MetricSample.sampled_at))
            .limit(20)
        )
        values = [float(value) for value in (await session.execute(history_query)).scalars().all()]
        values = list(reversed(values)) + [float(payload["value"])]
        for finding in self.detection_service.evaluate(values):
            await self.publisher.publish(
                ANOMALY_EVENTS_TOPIC,
                EventEnvelope(
                    event_type="anomaly.detected",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    source="worker.anomaly",
                    entity_id=str(uuid4()),
                    payload={
                        "anomaly_report": {
                            "id": str(uuid4()),
                            "anomaly_type": finding.anomaly_type,
                            "severity": finding.severity,
                            "entity_type": payload["entity_type"],
                            "entity_id": payload["entity_id"],
                            "score": finding.score,
                            "baseline_value": finding.baseline_value,
                            "observed_value": finding.observed_value,
                            "metadata": {
                                "reason": finding.reason,
                                "metric_name": payload["metric_name"],
                            },
                            "detected_at": utc_now(),
                            "status": "open",
                        }
                    },
                    metadata={"aggregate": "anomaly"},
                ),
            )

    async def _handle_cost_event(self, event: EventEnvelope, session: AsyncSession) -> None:
        payload = event.payload
        workflow_id = payload.get("workflow_id") or payload.get("execution_run_id")
        history_query = (
            select(CostRecord.usd_cost)
            .where(CostRecord.workflow_id == workflow_id)
            .order_by(desc(CostRecord.occurred_at))
            .limit(20)
        )
        values = [float(value) for value in (await session.execute(history_query)).scalars().all()]
        values = list(reversed(values)) + [float(payload["usd_cost"])]
        for finding in self.detection_service.evaluate(values):
            await self.publisher.publish(
                ANOMALY_EVENTS_TOPIC,
                EventEnvelope(
                    event_type="anomaly.detected",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    source="worker.anomaly",
                    entity_id=str(uuid4()),
                    payload={
                        "anomaly_report": {
                            "id": str(uuid4()),
                            "anomaly_type": finding.anomaly_type,
                            "severity": finding.severity,
                            "entity_type": "workflow",
                            "entity_id": str(workflow_id),
                            "score": finding.score,
                            "baseline_value": finding.baseline_value,
                            "observed_value": finding.observed_value,
                            "metadata": {"reason": finding.reason, "metric_name": "usd_cost"},
                            "detected_at": utc_now(),
                            "status": "open",
                        }
                    },
                    metadata={"aggregate": "anomaly"},
                ),
            )


class DriftHandler:
    def __init__(
        self, publisher: PublisherProtocol, detection_service: DriftDetectionService
    ) -> None:
        self.publisher = publisher
        self.detection_service = detection_service

    async def __call__(
        self, event: EventEnvelope, _record: Any, session: AsyncSession
    ) -> None:
        if event.event_type != "model.inference.recorded":
            return

        model_name = str(event.payload["model_name"])
        await self._evaluate_metric(
            session=session,
            event=event,
            metric_name="model_token_input",
            model_name=model_name,
        )
        await self._evaluate_metric(
            session=session,
            event=event,
            metric_name="model_token_output",
            model_name=model_name,
        )
        await self._evaluate_metric(
            session=session,
            event=event,
            metric_name="model_latency_ms",
            model_name=model_name,
        )

    async def _evaluate_metric(
        self,
        *,
        session: AsyncSession,
        event: EventEnvelope,
        metric_name: str,
        model_name: str,
    ) -> None:
        query = (
            select(MetricSample.value)
            .where(
                MetricSample.metric_name == metric_name,
                MetricSample.entity_type == "model",
                MetricSample.entity_id == model_name,
            )
            .order_by(desc(MetricSample.sampled_at))
            .limit(40)
        )
        values = [float(value) for value in (await session.execute(query)).scalars().all()]
        values = list(reversed(values))
        if len(values) < 20:
            return
        baseline = values[:20]
        current = values[-10:]
        for finding in self.detection_service.evaluate(baseline, current):
            await self.publisher.publish(
                DRIFT_EVENTS_TOPIC,
                EventEnvelope(
                    event_type="drift.detected",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    source="worker.drift",
                    entity_id=str(uuid4()),
                    payload={
                        "drift_report": {
                            "id": str(uuid4()),
                            "drift_type": finding.drift_type,
                            "severity": finding.severity,
                            "entity_type": "model",
                            "entity_id": model_name,
                            "metric_name": metric_name,
                            "score": finding.score,
                            "threshold": finding.threshold,
                            "metadata": {"reason": finding.reason},
                            "detected_at": utc_now(),
                            "status": "open",
                        }
                    },
                    metadata={"aggregate": "drift"},
                ),
            )


class AlertHandler:
    def __init__(self, service: AlertingService) -> None:
        self.service = service

    async def __call__(
        self, event: EventEnvelope, _record: Any, session: AsyncSession
    ) -> None:
        if event.event_type == "anomaly.detected":
            report = event.payload["anomaly_report"]
            await self.service.process_signal(
                session=session,
                signal_type="anomaly",
                source_event=event,
                severity=report["severity"],
                title=f"Anomaly detected: {report['anomaly_type']}",
                description=(
                    f"{report['entity_type']}={report['entity_id']} "
                    f"score={report['score']}"
                ),
                entity_type=report["entity_type"],
                entity_id=report["entity_id"],
            )
        elif event.event_type == "drift.detected":
            report = event.payload["drift_report"]
            await self.service.process_signal(
                session=session,
                signal_type="drift",
                source_event=event,
                severity=report["severity"],
                title=f"Drift detected: {report['drift_type']}",
                description=(
                    f"{report['entity_type']}={report['entity_id']} "
                    f"score={report['score']}"
                ),
                entity_type=report["entity_type"],
                entity_id=report["entity_id"],
            )


def build_workers(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: PublisherProtocol,
    projector: ProjectionService,
    anomaly_detection_service: AnomalyDetectionService,
    drift_detection_service: DriftDetectionService,
    alerting_service: AlertingService,
) -> dict[str, list[BaseConsumerWorker]]:
    return {
        "projection": [
            BaseConsumerWorker(
                name="projection-worker",
                group_id="projection-consumers",
                topics=[
                    REGISTRY_EVENTS_TOPIC,
                    AGENT_EXECUTIONS_TOPIC,
                    AGENT_STEPS_TOPIC,
                    SYSTEM_METRICS_TOPIC,
                    SYSTEM_HEALTH_TOPIC,
                    COST_EVENTS_TOPIC,
                    ANOMALY_EVENTS_TOPIC,
                    DRIFT_EVENTS_TOPIC,
                    ALERTS_EVENTS_TOPIC,
                    AUDIT_EVENTS_TOPIC,
                ],
                handler=cast(EventHandler, ProjectionHandler(projector)),
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            )
        ],
        "analytics": [
            BaseConsumerWorker(
                name="metrics-aggregation-worker",
                group_id="metrics-aggregation-consumers",
                topics=[AGENT_EXECUTIONS_TOPIC, AGENT_STEPS_TOPIC],
                handler=cast(EventHandler, MetricsAggregationHandler(publisher)),
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            ),
            BaseConsumerWorker(
                name="anomaly-worker",
                group_id="anomaly-consumers",
                topics=[SYSTEM_METRICS_TOPIC, COST_EVENTS_TOPIC],
                handler=cast(
                    EventHandler, AnomalyHandler(publisher, anomaly_detection_service)
                ),
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            ),
            BaseConsumerWorker(
                name="drift-worker",
                group_id="drift-consumers",
                topics=[MODEL_INFERENCE_TOPIC],
                handler=cast(EventHandler, DriftHandler(publisher, drift_detection_service)),
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            ),
        ],
        "alerts": [
            BaseConsumerWorker(
                name="alert-worker",
                group_id="alert-consumers",
                topics=[ANOMALY_EVENTS_TOPIC, DRIFT_EVENTS_TOPIC],
                handler=cast(EventHandler, AlertHandler(alerting_service)),
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            )
        ],
    }

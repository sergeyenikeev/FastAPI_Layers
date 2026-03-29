from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base, utc_now
from app.db.models import (
    Agent,
    AgentVersion,
    Alert,
    AnomalyReport,
    AuditEvent,
    CostRecord,
    Deployment,
    DriftReport,
    Environment,
    ExecutionRun,
    ExecutionStep,
    GraphDefinition,
    HealthCheckResult,
    MetricSample,
    ModelEndpoint,
    ModelVersion,
    ToolDefinition,
    WorkerHeartbeat,
)
from app.domain.events import EventEnvelope


def parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


class ProjectionService:
    async def apply(self, session: AsyncSession, event: EventEnvelope) -> None:
        # Event type is mapped to a handler by naming convention. This keeps the dispatch
        # table compact and makes new projection handlers easy to add incrementally.
        handler_name = event.event_type.replace(".", "_")
        handler = getattr(self, f"_handle_{handler_name}", None)
        if handler is None:
            return
        await handler(session, event)

    async def _handle_agent_created(self, session: AsyncSession, event: EventEnvelope) -> None:
        agent_payload = event.payload["agent"]
        version_payload = event.payload["agent_version"]
        await self._upsert(session, Agent, agent_payload)
        await self._upsert(session, AgentVersion, version_payload)

    async def _handle_agent_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(session, Agent, event.payload["agent_id"], event.payload["changes"])

    async def _handle_agent_deleted(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._delete(session, Agent, event.payload["agent_id"])

    async def _handle_model_registered(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._upsert(session, ModelEndpoint, event.payload["model_endpoint"])
        await self._upsert(session, ModelVersion, event.payload["model_version"])

    async def _handle_model_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(
            session,
            ModelEndpoint,
            event.payload["model_endpoint_id"],
            event.payload["changes"],
        )

    async def _handle_model_deleted(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._delete(session, ModelEndpoint, event.payload["model_endpoint_id"])

    async def _handle_graph_created(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._upsert(session, GraphDefinition, event.payload["graph_definition"])

    async def _handle_graph_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(
            session,
            GraphDefinition,
            event.payload["graph_definition_id"],
            event.payload["changes"],
        )

    async def _handle_graph_deleted(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._delete(session, GraphDefinition, event.payload["graph_definition_id"])

    async def _handle_deployment_created(self, session: AsyncSession, event: EventEnvelope) -> None:
        if "environment" in event.payload:
            await self._upsert(session, Environment, event.payload["environment"])
        await self._upsert(session, Deployment, event.payload["deployment"])

    async def _handle_deployment_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(
            session, Deployment, event.payload["deployment_id"], event.payload["changes"]
        )

    async def _handle_deployment_deleted(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._delete(session, Deployment, event.payload["deployment_id"])

    async def _handle_tool_created(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._upsert(session, ToolDefinition, event.payload["tool_definition"])

    async def _handle_tool_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(
            session,
            ToolDefinition,
            event.payload["tool_definition_id"],
            event.payload["changes"],
        )

    async def _handle_tool_deleted(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._delete(session, ToolDefinition, event.payload["tool_definition_id"])

    async def _handle_environment_created(
        self, session: AsyncSession, event: EventEnvelope
    ) -> None:
        await self._upsert(session, Environment, event.payload["environment"])

    async def _handle_environment_updated(
        self, session: AsyncSession, event: EventEnvelope
    ) -> None:
        await self._update(
            session, Environment, event.payload["environment_id"], event.payload["changes"]
        )

    async def _handle_environment_deleted(
        self, session: AsyncSession, event: EventEnvelope
    ) -> None:
        await self._delete(session, Environment, event.payload["environment_id"])

    async def _handle_execution_started(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload["execution_run"])
        payload["started_at"] = parse_datetime(payload.get("started_at"))
        payload["finished_at"] = parse_datetime(payload.get("finished_at"))
        # CQRS read side must tolerate eventual consistency: referenced deployment or
        # graph rows may not exist locally yet if their own projection lags behind.
        payload["deployment_id"] = await self._resolve_fk_or_none(
            session, Deployment, payload.get("deployment_id")
        )
        payload["graph_definition_id"] = await self._resolve_fk_or_none(
            session, GraphDefinition, payload.get("graph_definition_id")
        )
        await self._upsert(session, ExecutionRun, payload)

    async def _handle_execution_finished(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._update(
            session,
            ExecutionRun,
            event.payload["execution_run_id"],
            {
                "status": event.payload["status"],
                "output_payload": event.payload["output_payload"],
                "finished_at": parse_datetime(event.payload["finished_at"]),
                "error_message": event.payload.get("error_message"),
            },
        )

    async def _handle_execution_failed(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._handle_execution_finished(session, event)

    async def _handle_step_completed(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload["execution_step"])
        payload["started_at"] = parse_datetime(payload.get("started_at"))
        payload["finished_at"] = parse_datetime(payload.get("finished_at"))
        # Step events can arrive before execution.started is materialized in the local
        # read model, so we create a placeholder run to keep FK constraints satisfied.
        await self._ensure_execution_run_placeholder(
            session=session,
            execution_run_id=payload["execution_run_id"],
            correlation_id=event.correlation_id,
            trace_id=str(payload.get("trace_id", event.trace_id)),
            started_at=payload.get("started_at"),
            input_payload={},
        )
        await self._upsert(session, ExecutionStep, payload)

    async def _handle_health_recorded(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload)
        payload["id"] = event.event_id
        payload["checked_at"] = parse_datetime(payload["checked_at"])
        await self._upsert(session, HealthCheckResult, payload)

    async def _handle_metric_recorded(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload)
        payload["id"] = event.event_id
        payload["sampled_at"] = parse_datetime(payload["sampled_at"])
        await self._upsert(session, MetricSample, payload)

    async def _handle_cost_recorded(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload)
        payload["id"] = event.event_id
        payload["occurred_at"] = parse_datetime(payload["occurred_at"])
        execution_run_id = payload.get("execution_run_id")
        if execution_run_id and await session.get(ExecutionRun, execution_run_id) is None:
            payload["execution_run_id"] = None
        await self._upsert(session, CostRecord, payload)

    async def _handle_anomaly_detected(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload["anomaly_report"])
        payload["metadata_json"] = payload.pop("metadata", {})
        payload["detected_at"] = parse_datetime(payload["detected_at"])
        await self._upsert(session, AnomalyReport, payload)

    async def _handle_drift_detected(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload["drift_report"])
        payload["metadata_json"] = payload.pop("metadata", {})
        payload["detected_at"] = parse_datetime(payload["detected_at"])
        await self._upsert(session, DriftReport, payload)

    async def _handle_alert_created(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._upsert_alert(session, event.payload["alert"])

    async def _handle_alert_updated(self, session: AsyncSession, event: EventEnvelope) -> None:
        await self._upsert_alert(session, event.payload["alert"])

    async def _handle_audit_recorded(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = event.payload
        await self._upsert(
            session,
            AuditEvent,
            {
                "id": event.event_id,
                "actor": payload["actor"],
                "action": payload["action"],
                "entity_type": payload["entity_type"],
                "entity_id": payload["entity_id"],
                "correlation_id": event.correlation_id,
                "trace_id": event.trace_id,
                "payload": json_safe(payload["payload"]),
                "created_at": event.timestamp,
            },
        )

    async def _handle_worker_heartbeat(self, session: AsyncSession, event: EventEnvelope) -> None:
        payload = dict(event.payload)
        payload["metadata_json"] = payload.pop("metadata", {})
        payload["last_seen_at"] = parse_datetime(payload["last_seen_at"])
        await self._upsert(session, WorkerHeartbeat, payload)

    async def _upsert(
        self, session: AsyncSession, model_cls: type[Base], payload: dict[str, Any]
    ) -> None:
        # Projection payloads often contain nested JSON; we normalize them before writing
        # so ORM entities receive JSON-safe values independent of event source details.
        payload = {
            field: json_safe(value) if isinstance(value, (dict, list, tuple)) else value
            for field, value in payload.items()
        }
        entity = await session.get(model_cls, payload["id"])
        if entity is None:
            session.add(model_cls(**payload))
            return
        for field, value in payload.items():
            setattr(entity, field, value)

    async def _delete(
        self, session: AsyncSession, model_cls: type[Base], entity_id: str
    ) -> None:
        entity = await session.get(model_cls, entity_id)
        if entity is not None:
            await session.delete(entity)

    async def _update(
        self,
        session: AsyncSession,
        model_cls: type[Base],
        entity_id: str,
        changes: dict[str, Any],
    ) -> None:
        # Missing rows are ignored intentionally: projection workers must remain tolerant
        # to reordering and partial history instead of crashing on absent read-side state.
        entity = await session.get(model_cls, entity_id)
        if entity is None:
            return
        for field, value in changes.items():
            setattr(
                entity, field, json_safe(value) if isinstance(value, (dict, list, tuple)) else value
            )

    async def _upsert_alert(self, session: AsyncSession, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload["last_sent_at"] = parse_datetime(payload.get("last_sent_at"))
        entity = await session.get(Alert, payload["id"])
        if entity is None:
            session.add(Alert(**payload))
            return
        for field, value in payload.items():
            setattr(entity, field, value)

    async def _resolve_fk_or_none(
        self,
        session: AsyncSession,
        model_cls: type[Base],
        entity_id: str | None,
    ) -> str | None:
        if not entity_id:
            return None
        if await session.get(model_cls, entity_id) is None:
            return None
        return entity_id

    async def _ensure_execution_run_placeholder(
        self,
        *,
        session: AsyncSession,
        execution_run_id: str,
        correlation_id: str,
        trace_id: str,
        started_at: datetime | None,
        input_payload: dict[str, Any],
    ) -> None:
        if await session.get(ExecutionRun, execution_run_id) is not None:
            return
        # Placeholder rows let out-of-order step events survive until the proper terminal
        # or started event arrives and enriches the execution record with full context.
        session.add(
            ExecutionRun(
                id=execution_run_id,
                deployment_id=None,
                graph_definition_id=None,
                status="running",
                input_payload=input_payload,
                output_payload=None,
                started_at=started_at or utc_now(),
                finished_at=None,
                correlation_id=correlation_id,
                trace_id=trace_id,
                error_message=None,
            )
        )

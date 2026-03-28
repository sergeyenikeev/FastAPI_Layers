from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.context import get_correlation_id, get_trace_id
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.core.metrics import ACTIVE_EXECUTIONS, COMPUTE_CALL_COST, EXECUTION_STEP_DURATION
from app.db.base import utc_now
from app.db.models import Deployment, ModelVersion
from app.domain.enums import ExecutionStatus
from app.domain.events import EventEnvelope
from app.domain.schemas import CommandAccepted
from app.messaging.kafka import PublisherProtocol
from app.messaging.topics import (
    AGENT_EXECUTIONS_TOPIC,
    AGENT_STEPS_TOPIC,
    COST_EVENTS_TOPIC,
    MODEL_INFERENCE_TOPIC,
    SYSTEM_METRICS_TOPIC,
)
from app.modules.audit.service import AuditService
from app.modules.orchestration.gateway import ModelGateway
from app.modules.orchestration.graph import ExecutionState, ExecutionWorkflow
from app.modules.orchestration.schemas import CreateExecutionRequest

logger = get_logger(__name__)


class ExecutionCommandService:
    def __init__(
        self,
        publisher: PublisherProtocol,
        audit_service: AuditService,
        model_gateway: ModelGateway,
        task_spawner: Callable[[Awaitable[None]], asyncio.Task[None]],
    ) -> None:
        self.publisher = publisher
        self.audit_service = audit_service
        self.model_gateway = model_gateway
        self.task_spawner = task_spawner

    async def create_execution(
        self,
        session: AsyncSession,
        payload: CreateExecutionRequest,
    ) -> CommandAccepted:
        if not payload.deployment_id and not payload.graph_definition_id:
            raise DomainError(
                "deployment_id or graph_definition_id must be provided",
                code="missing_execution_target",
            )

        model_context: dict[str, Any] = {}
        graph_definition_id = payload.graph_definition_id
        if payload.deployment_id:
            deployment = await self._load_deployment(session, payload.deployment_id)
            if deployment is None:
                raise DomainError(
                    "Deployment not found",
                    code="not_found",
                    extra={"deployment_id": payload.deployment_id},
                )
            if deployment.agent_version and deployment.agent_version.graph_definition_id:
                graph_definition_id = (
                    graph_definition_id or deployment.agent_version.graph_definition_id
                )
            if deployment.model_version and deployment.model_version.model_endpoint:
                endpoint = deployment.model_version.model_endpoint
                model_context = {
                    "endpoint_url": endpoint.base_url,
                    "provider": endpoint.provider,
                    "model_name": deployment.model_version.model_name,
                    "pricing": deployment.model_version.pricing,
                    "agent_id": (
                        deployment.agent_version.agent_id if deployment.agent_version else None
                    ),
                    "environment_id": deployment.environment_id,
                    "workflow_id": graph_definition_id,
                }

        execution_run_id = str(uuid4())
        event = EventEnvelope(
            event_type="execution.started",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.orchestration",
            entity_id=execution_run_id,
            payload={
                "execution_run": {
                    "id": execution_run_id,
                    "deployment_id": payload.deployment_id,
                    "graph_definition_id": graph_definition_id,
                    "status": ExecutionStatus.RUNNING,
                    "input_payload": payload.input_payload,
                    "output_payload": None,
                    "started_at": utc_now(),
                    "finished_at": None,
                    "correlation_id": get_correlation_id(),
                    "trace_id": get_trace_id(),
                    "error_message": None,
                },
                "metadata": payload.metadata,
            },
            metadata={"aggregate": "execution"},
        )
        await self.publisher.publish(AGENT_EXECUTIONS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="execution.start",
            entity_type="execution_run",
            entity_id=execution_run_id,
            payload=event.payload,
        )

        self.task_spawner(
            self._run_workflow(
                execution_run_id=execution_run_id,
                deployment_id=payload.deployment_id,
                graph_definition_id=graph_definition_id,
                input_payload=payload.input_payload,
                model_context=model_context,
            )
        )
        return CommandAccepted(
            entity_id=execution_run_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def _load_deployment(
        self, session: AsyncSession, deployment_id: str
    ) -> Deployment | None:
        query = (
            select(Deployment)
            .options(
                joinedload(Deployment.agent_version),
                joinedload(Deployment.model_version).joinedload(ModelVersion.model_endpoint),
            )
            .where(Deployment.id == deployment_id)
        )
        return (await session.execute(query)).scalar_one_or_none()

    async def _run_workflow(
        self,
        *,
        execution_run_id: str,
        deployment_id: str | None,
        graph_definition_id: str | None,
        input_payload: dict[str, Any],
        model_context: dict[str, Any],
    ) -> None:
        ACTIVE_EXECUTIONS.inc()
        workflow = ExecutionWorkflow(
            self.model_gateway, self._step_emitter(execution_run_id, model_context)
        )
        try:
            state: ExecutionState = {
                "execution_run_id": execution_run_id,
                "deployment_id": deployment_id,
                "graph_definition_id": graph_definition_id,
                "input_payload": input_payload,
                "objective": str(input_payload.get("objective", "No objective provided")),
                "model_context": model_context,
            }
            result = await workflow.invoke(state)
            finished_event = EventEnvelope(
                event_type="execution.finished",
                correlation_id=get_correlation_id(),
                trace_id=get_trace_id(),
                source="worker.orchestration",
                entity_id=execution_run_id,
                payload={
                    "execution_run_id": execution_run_id,
                    "status": ExecutionStatus.SUCCEEDED,
                    "output_payload": result.get("final_output", {}),
                    "finished_at": utc_now(),
                    "error_message": None,
                },
                metadata={"aggregate": "execution"},
            )
            await self.publisher.publish(AGENT_EXECUTIONS_TOPIC, finished_event)
            await self.audit_service.publish_audit_event(
                action="execution.finish",
                entity_type="execution_run",
                entity_id=execution_run_id,
                payload=finished_event.payload,
            )
        except Exception as exc:  # pragma: no cover - exception path validated by service tests
            logger.exception(
                "execution.workflow_failed", execution_run_id=execution_run_id, error=str(exc)
            )
            failed_event = EventEnvelope(
                event_type="execution.failed",
                correlation_id=get_correlation_id(),
                trace_id=get_trace_id(),
                source="worker.orchestration",
                entity_id=execution_run_id,
                payload={
                    "execution_run_id": execution_run_id,
                    "status": ExecutionStatus.FAILED,
                    "output_payload": None,
                    "finished_at": utc_now(),
                    "error_message": str(exc),
                },
                metadata={"aggregate": "execution"},
            )
            await self.publisher.publish(AGENT_EXECUTIONS_TOPIC, failed_event)
            await self.audit_service.publish_audit_event(
                action="execution.fail",
                entity_type="execution_run",
                entity_id=execution_run_id,
                payload=failed_event.payload,
            )
        finally:
            ACTIVE_EXECUTIONS.dec()

    def _step_emitter(
        self,
        execution_run_id: str,
        model_context: dict[str, Any],
    ) -> Callable[[str, str, dict[str, Any], dict[str, Any], int, float], Awaitable[None]]:
        async def _emit(
            step_name: str,
            agent_name: str,
            input_payload: dict[str, Any],
            output_payload: dict[str, Any],
            token_usage_total: int,
            duration_ms: float,
        ) -> None:
            finished_at = utc_now()
            started_at = finished_at - timedelta(milliseconds=duration_ms)
            sanitized_output = {
                key: value for key, value in output_payload.items() if key != "_telemetry"
            }
            telemetry = output_payload.get("_telemetry", {})

            event = EventEnvelope(
                event_type="step.completed",
                correlation_id=get_correlation_id(),
                trace_id=get_trace_id(),
                source="worker.orchestration",
                entity_id=str(uuid4()),
                payload={
                    "execution_step": {
                        "id": str(uuid4()),
                        "execution_run_id": execution_run_id,
                        "agent_name": agent_name,
                        "step_name": step_name,
                        "status": ExecutionStatus.SUCCEEDED,
                        "input_payload": input_payload,
                        "output_payload": sanitized_output,
                        "duration_ms": duration_ms,
                        "token_usage_total": token_usage_total,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "trace_id": get_trace_id(),
                    }
                },
                metadata={"aggregate": "execution_step"},
            )
            await self.publisher.publish(AGENT_STEPS_TOPIC, event)
            EXECUTION_STEP_DURATION.labels(
                agent_name, step_name, ExecutionStatus.SUCCEEDED
            ).observe(duration_ms / 1000)

            await self._publish_metric(
                "step_duration_ms", "execution_step", execution_run_id, duration_ms
            )
            await self._publish_metric(
                "step_token_usage", "execution_step", execution_run_id, token_usage_total
            )

            if telemetry:
                model_name = str(telemetry.get("model_name", "unknown"))
                await self._publish_metric(
                    "model_latency_ms",
                    "model",
                    model_name,
                    float(telemetry.get("latency_ms", duration_ms)),
                )
                await self._publish_metric(
                    "model_token_input",
                    "model",
                    model_name,
                    float(telemetry.get("token_input", 0)),
                )
                await self._publish_metric(
                    "model_token_output",
                    "model",
                    model_name,
                    float(telemetry.get("token_output", 0)),
                )
                await self.publisher.publish(
                    MODEL_INFERENCE_TOPIC,
                    EventEnvelope(
                        event_type="model.inference.recorded",
                        correlation_id=get_correlation_id(),
                        trace_id=get_trace_id(),
                        source="worker.orchestration",
                        entity_id=execution_run_id,
                        payload={
                            "execution_run_id": execution_run_id,
                            "step_name": step_name,
                            "agent_name": agent_name,
                            "provider": telemetry.get("provider"),
                            "model_name": model_name,
                            "latency_ms": telemetry.get("latency_ms", duration_ms),
                            "token_input": telemetry.get("token_input", 0),
                            "token_output": telemetry.get("token_output", 0),
                        },
                        metadata={"aggregate": "model_inference"},
                    ),
                )
                cost_usd = float(telemetry.get("cost_usd", 0.0))
                COMPUTE_CALL_COST.labels(
                    str(model_context.get("agent_id", "unknown")),
                    str(model_context.get("workflow_id", "unknown")),
                    str(model_context.get("environment_id", "unknown")),
                ).inc(cost_usd)
                await self.publisher.publish(
                    COST_EVENTS_TOPIC,
                    EventEnvelope(
                        event_type="cost.recorded",
                        correlation_id=get_correlation_id(),
                        trace_id=get_trace_id(),
                        source="worker.orchestration",
                        entity_id=execution_run_id,
                        payload={
                            "execution_run_id": execution_run_id,
                            "agent_id": model_context.get("agent_id"),
                            "workflow_id": model_context.get("workflow_id"),
                            "environment_id": model_context.get("environment_id"),
                            "usd_cost": cost_usd,
                            "token_input": telemetry.get("token_input", 0),
                            "token_output": telemetry.get("token_output", 0),
                            "provider": telemetry.get("provider"),
                            "model_name": telemetry.get("model_name"),
                            "occurred_at": finished_at,
                        },
                        metadata={"aggregate": "cost"},
                    ),
                )

        return _emit

    async def _publish_metric(
        self,
        metric_name: str,
        entity_type: str,
        entity_id: str,
        value: float,
    ) -> None:
        await self.publisher.publish(
            SYSTEM_METRICS_TOPIC,
            EventEnvelope(
                event_type="metric.recorded",
                correlation_id=get_correlation_id(),
                trace_id=get_trace_id(),
                source="worker.orchestration",
                entity_id=entity_id,
                payload={
                    "metric_name": metric_name,
                    "metric_type": "gauge",
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "value": value,
                    "tags": {"service": "orchestration"},
                    "sampled_at": utc_now(),
                },
                metadata={"aggregate": "metric"},
            ),
        )

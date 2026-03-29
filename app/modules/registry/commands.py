from __future__ import annotations

from uuid import uuid4

from app.core.context import get_correlation_id, get_trace_id
from app.domain.events import EventEnvelope
from app.domain.schemas import CommandAccepted
from app.messaging.kafka import PublisherProtocol
from app.messaging.topics import REGISTRY_EVENTS_TOPIC
from app.modules.audit.service import AuditService
from app.modules.registry.schemas import (
    CreateAgentRequest,
    CreateDeploymentRequest,
    CreateEnvironmentRequest,
    CreateGraphRequest,
    CreateModelRequest,
    CreateToolRequest,
    UpdateAgentRequest,
    UpdateDeploymentRequest,
    UpdateEnvironmentRequest,
    UpdateGraphRequest,
    UpdateModelRequest,
    UpdateToolRequest,
)


class RegistryCommandService:
    # RegistryCommandService — write-side фасад реестра. Он не пишет в read-side
    # таблицы напрямую, а публикует domain events и тем самым сохраняет единый
    # event-driven поток для materialization, audit и downstream consumers.
    def __init__(self, publisher: PublisherProtocol, audit_service: AuditService):
        self.publisher = publisher
        self.audit_service = audit_service

    async def create_agent(self, payload: CreateAgentRequest) -> CommandAccepted:
        # Создание агента сразу включает и первую версию агента, потому что для
        # платформы агент без версии не является исполнимой конфигурацией.
        agent_id = str(uuid4())
        agent_version_id = str(uuid4())
        event = EventEnvelope(
            event_type="agent.created",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=agent_id,
            payload={
                "agent": {
                    "id": agent_id,
                    "name": payload.name,
                    "description": payload.description,
                    "owner": payload.owner,
                    "status": "active",
                    "tags": payload.tags,
                },
                "agent_version": {
                    "id": agent_version_id,
                    "agent_id": agent_id,
                    "graph_definition_id": payload.graph_definition_id,
                    "version": payload.version,
                    "runtime_config": payload.runtime_config,
                    "is_active": True,
                },
            },
            metadata={"aggregate": "agent"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="agent.create",
            entity_type="agent",
            entity_id=agent_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=agent_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_agent(self, agent_id: str, payload: UpdateAgentRequest) -> CommandAccepted:
        event = EventEnvelope(
            event_type="agent.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=agent_id,
            payload={"agent_id": agent_id, "changes": payload.model_dump(exclude_none=True)},
            metadata={"aggregate": "agent"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="agent.update",
            entity_type="agent",
            entity_id=agent_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=agent_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_agent(self, agent_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="agent.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=agent_id,
            payload={"agent_id": agent_id},
            metadata={"aggregate": "agent"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="agent.delete",
            entity_type="agent",
            entity_id=agent_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=agent_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def create_model(self, payload: CreateModelRequest) -> CommandAccepted:
        # Модель тоже публикуется как пара endpoint + version, чтобы orchestration
        # мог стабильно ссылаться на конкретную версию inference-конфига.
        endpoint_id = str(uuid4())
        version_id = str(uuid4())
        event = EventEnvelope(
            event_type="model.registered",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=endpoint_id,
            payload={
                "model_endpoint": {
                    "id": endpoint_id,
                    "name": payload.name,
                    "provider": payload.provider,
                    "base_url": payload.base_url,
                    "auth_type": payload.auth_type,
                    "status": "active",
                    "capabilities": payload.capabilities,
                },
                "model_version": {
                    "id": version_id,
                    "model_endpoint_id": endpoint_id,
                    "version": payload.version,
                    "model_name": payload.model_name,
                    "tokenizer_name": payload.tokenizer_name,
                    "context_window": payload.context_window,
                    "pricing": payload.pricing,
                    "is_default": payload.is_default,
                },
            },
            metadata={"aggregate": "model"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="model.register",
            entity_type="model_endpoint",
            entity_id=endpoint_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=endpoint_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_model(self, model_id: str, payload: UpdateModelRequest) -> CommandAccepted:
        event = EventEnvelope(
            event_type="model.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=model_id,
            payload={
                "model_endpoint_id": model_id,
                "changes": payload.model_dump(exclude_none=True),
            },
            metadata={"aggregate": "model"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="model.update",
            entity_type="model_endpoint",
            entity_id=model_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=model_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_model(self, model_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="model.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=model_id,
            payload={"model_endpoint_id": model_id},
            metadata={"aggregate": "model"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="model.delete",
            entity_type="model_endpoint",
            entity_id=model_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=model_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def create_graph(self, payload: CreateGraphRequest) -> CommandAccepted:
        # Graph definition materializes отдельно от agent, чтобы один сценарий
        # выполнения мог переиспользоваться несколькими агентами и deployment-ами.
        graph_id = str(uuid4())
        event = EventEnvelope(
            event_type="graph.created",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=graph_id,
            payload={
                "graph_definition": {
                    "id": graph_id,
                    "name": payload.name,
                    "description": payload.description,
                    "version": payload.version,
                    "entrypoint": payload.entrypoint,
                    "definition": payload.definition,
                }
            },
            metadata={"aggregate": "graph"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="graph.create",
            entity_type="graph_definition",
            entity_id=graph_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=graph_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_graph(self, graph_id: str, payload: UpdateGraphRequest) -> CommandAccepted:
        event = EventEnvelope(
            event_type="graph.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=graph_id,
            payload={
                "graph_definition_id": graph_id,
                "changes": payload.model_dump(exclude_none=True),
            },
            metadata={"aggregate": "graph"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="graph.update",
            entity_type="graph_definition",
            entity_id=graph_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=graph_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_graph(self, graph_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="graph.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=graph_id,
            payload={"graph_definition_id": graph_id},
            metadata={"aggregate": "graph"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="graph.delete",
            entity_type="graph_definition",
            entity_id=graph_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=graph_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def create_deployment(self, payload: CreateDeploymentRequest) -> CommandAccepted:
        # Deployment связывает agent version, model version и environment в одну
        # исполнимую конфигурацию. Именно по deployment чаще всего стартует execution.
        deployment_id = str(uuid4())
        environment_id = payload.environment_id or str(uuid4())
        event = EventEnvelope(
            event_type="deployment.created",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=deployment_id,
            payload={
                "environment": {
                    "id": environment_id,
                    "name": payload.environment_name,
                    "description": payload.environment_description,
                    "labels": {"managed_by": "workflow-platform"},
                },
                "deployment": {
                    "id": deployment_id,
                    "agent_version_id": payload.agent_version_id,
                    "environment_id": environment_id,
                    "model_version_id": payload.model_version_id,
                    "status": "pending",
                    "replica_count": payload.replica_count,
                    "configuration": payload.configuration,
                },
            },
            metadata={"aggregate": "deployment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="deployment.create",
            entity_type="deployment",
            entity_id=deployment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=deployment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_deployment(
        self, deployment_id: str, payload: UpdateDeploymentRequest
    ) -> CommandAccepted:
        event = EventEnvelope(
            event_type="deployment.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=deployment_id,
            payload={
                "deployment_id": deployment_id,
                "changes": payload.model_dump(exclude_none=True),
            },
            metadata={"aggregate": "deployment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="deployment.update",
            entity_type="deployment",
            entity_id=deployment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=deployment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_deployment(self, deployment_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="deployment.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=deployment_id,
            payload={"deployment_id": deployment_id},
            metadata={"aggregate": "deployment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="deployment.delete",
            entity_type="deployment",
            entity_id=deployment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=deployment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def create_tool(self, payload: CreateToolRequest) -> CommandAccepted:
        # Tool definitions пока не участвуют напрямую в runtime wiring, но уже
        # живут в registry и versionable event stream, чтобы workflow можно было
        # постепенно переводить на декларативное описание инструментов.
        tool_id = str(uuid4())
        event = EventEnvelope(
            event_type="tool.created",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=tool_id,
            payload={
                "tool_definition": {
                    "id": tool_id,
                    "name": payload.name,
                    "description": payload.description,
                    "schema_json": payload.schema_definition,
                    "implementation_path": payload.implementation_path,
                }
            },
            metadata={"aggregate": "tool"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="tool.create",
            entity_type="tool_definition",
            entity_id=tool_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=tool_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_tool(self, tool_id: str, payload: UpdateToolRequest) -> CommandAccepted:
        event = EventEnvelope(
            event_type="tool.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=tool_id,
            payload={
                "tool_definition_id": tool_id,
                "changes": payload.model_dump(exclude_none=True, by_alias=True),
            },
            metadata={"aggregate": "tool"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="tool.update",
            entity_type="tool_definition",
            entity_id=tool_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=tool_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_tool(self, tool_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="tool.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=tool_id,
            payload={"tool_definition_id": tool_id},
            metadata={"aggregate": "tool"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="tool.delete",
            entity_type="tool_definition",
            entity_id=tool_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=tool_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def create_environment(self, payload: CreateEnvironmentRequest) -> CommandAccepted:
        # Environment создается как самостоятельная registry-сущность, потому что
        # оно участвует и в deployment, и в cost attribution, и в monitoring срезах.
        environment_id = str(uuid4())
        event = EventEnvelope(
            event_type="environment.created",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=environment_id,
            payload={
                "environment": {
                    "id": environment_id,
                    "name": payload.name,
                    "description": payload.description,
                    "labels": payload.labels,
                }
            },
            metadata={"aggregate": "environment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="environment.create",
            entity_type="environment",
            entity_id=environment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=environment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def update_environment(
        self, environment_id: str, payload: UpdateEnvironmentRequest
    ) -> CommandAccepted:
        event = EventEnvelope(
            event_type="environment.updated",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=environment_id,
            payload={
                "environment_id": environment_id,
                "changes": payload.model_dump(exclude_none=True),
            },
            metadata={"aggregate": "environment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="environment.update",
            entity_type="environment",
            entity_id=environment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=environment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

    async def delete_environment(self, environment_id: str) -> CommandAccepted:
        event = EventEnvelope(
            event_type="environment.deleted",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api.registry",
            entity_id=environment_id,
            payload={"environment_id": environment_id},
            metadata={"aggregate": "environment"},
        )
        await self.publisher.publish(REGISTRY_EVENTS_TOPIC, event)
        await self.audit_service.publish_audit_event(
            action="environment.delete",
            entity_type="environment",
            entity_id=environment_id,
            payload=event.payload,
        )
        return CommandAccepted(
            entity_id=environment_id,
            event_id=event.event_id,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
        )

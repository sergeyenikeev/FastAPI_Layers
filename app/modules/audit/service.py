from __future__ import annotations

from typing import Any

from app.core.context import get_correlation_id, get_principal_id, get_trace_id
from app.domain.events import EventEnvelope
from app.messaging.kafka import PublisherProtocol
from app.messaging.topics import AUDIT_EVENTS_TOPIC


class AuditService:
    def __init__(self, publisher: PublisherProtocol) -> None:
        self.publisher = publisher

    async def publish_audit_event(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> EventEnvelope:
        event = EventEnvelope(
            event_type="audit.recorded",
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
            source="api",
            entity_id=entity_id,
            payload={
                "actor": get_principal_id(),
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
            },
            metadata={"module": "audit"},
        )
        await self.publisher.publish(AUDIT_EVENTS_TOPIC, event)
        return event

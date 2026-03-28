from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.base import utc_now
from app.db.models import Alert
from app.domain.enums import AlertSeverity, AlertStatus
from app.domain.events import EventEnvelope
from app.messaging.kafka import PublisherProtocol
from app.messaging.topics import ALERTS_EVENTS_TOPIC

logger = get_logger(__name__)


class AlertingService:
    def __init__(self, publisher: PublisherProtocol, settings: Settings) -> None:
        self.publisher = publisher
        self.settings = settings

    async def process_signal(
        self,
        *,
        session: AsyncSession,
        signal_type: str,
        source_event: EventEnvelope,
        severity: str,
        title: str,
        description: str,
        entity_type: str,
        entity_id: str,
    ) -> EventEnvelope | None:
        dedupe_key = f"{signal_type}:{entity_type}:{entity_id}:{title}"
        existing = await self._find_existing_alert(session, dedupe_key)
        now = utc_now()
        if (
            existing
            and existing.last_sent_at
            and now - existing.last_sent_at
            < timedelta(seconds=self.settings.alert_cooldown_seconds)
        ):
            logger.info("alert.cooldown_skip", dedupe_key=dedupe_key)
            return None

        alert_id = existing.id if existing else str(uuid4())
        payload = {
            "alert": {
                "id": alert_id,
                "severity": severity,
                "dedupe_key": dedupe_key,
                "source_event_id": source_event.event_id,
                "title": title,
                "description": description,
                "status": AlertStatus.OPEN,
                "last_sent_at": now,
            }
        }
        event_type = "alert.updated" if existing else "alert.created"
        event = EventEnvelope(
            event_type=event_type,
            correlation_id=source_event.correlation_id,
            trace_id=source_event.trace_id,
            source="worker.alerting",
            entity_id=alert_id,
            payload=payload,
            metadata={"aggregate": "alert"},
        )
        await self.publisher.publish(ALERTS_EVENTS_TOPIC, event)
        await self._dispatch_notifications(severity, title, description)
        return event

    async def _find_existing_alert(self, session: AsyncSession, dedupe_key: str) -> Alert | None:
        query = select(Alert).where(Alert.dedupe_key == dedupe_key)
        return (await session.execute(query)).scalar_one_or_none()

    async def _dispatch_notifications(self, severity: str, title: str, description: str) -> None:
        logger.warning("alert.dispatched", severity=severity, title=title, description=description)
        if self.settings.default_alert_webhook:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        self.settings.default_alert_webhook,
                        json={"severity": severity, "title": title, "description": description},
                    )
            except Exception as exc:  # pragma: no cover - external dependency
                logger.warning("alert.webhook_failed", error=str(exc))

        if self.settings.default_alert_email:
            logger.info(
                "alert.email_stub",
                target=self.settings.default_alert_email,
                severity=severity,
                title=title,
            )


def severity_from_score(score: float) -> str:
    if score >= 3:
        return AlertSeverity.CRITICAL
    if score >= 1.5:
        return AlertSeverity.WARNING
    return AlertSeverity.INFO

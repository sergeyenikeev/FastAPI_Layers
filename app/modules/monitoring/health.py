from __future__ import annotations

from datetime import timedelta
from inspect import isawaitable

import httpx
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.base import utc_now
from app.db.models import WorkerHeartbeat
from app.domain.events import EventEnvelope
from app.messaging.kafka import PublisherProtocol
from app.messaging.topics import SYSTEM_HEALTH_TOPIC
from app.modules.monitoring.schemas import ComponentHealth, HealthSummary


class HealthService:
    def __init__(self, settings: Settings, engine: AsyncEngine, publisher: PublisherProtocol) -> None:
        self.settings = settings
        self.engine = engine
        self.publisher = publisher

    async def live(self) -> HealthSummary:
        return HealthSummary(
            status="passing",
            components=[
                ComponentHealth(
                    component="api",
                    status="passing",
                    details={"message": "process alive"},
                    checked_at=utc_now(),
                )
            ],
        )

    async def ready(self, session: AsyncSession) -> HealthSummary:
        components = [
            await self._check_db(),
            await self._check_redis(),
            self._check_kafka_state(),
            await self._check_workers(session),
        ]
        status = "passing" if all(c.status != "failing" for c in components) else "failing"
        return HealthSummary(status=status, components=components)

    async def deep(self, session: AsyncSession) -> HealthSummary:
        components = [
            await self._check_db(),
            await self._check_redis(),
            self._check_kafka_state(),
            await self._check_workers(session),
        ]
        for url in self.settings.model_probe_urls:
            components.append(await self._check_model_endpoint(url))

        status = "passing"
        if any(component.status == "failing" for component in components):
            status = "failing"
        elif any(component.status == "degraded" for component in components):
            status = "degraded"

        for component in components:
            await self.publisher.publish(
                SYSTEM_HEALTH_TOPIC,
                EventEnvelope(
                    event_type="health.recorded",
                    correlation_id="health-check",
                    trace_id="health-check",
                    source="api.health",
                    entity_id=component.component,
                    payload=component.model_dump(mode="json"),
                    metadata={"aggregate": "health"},
                ),
            )
        return HealthSummary(status=status, components=components)

    async def _check_db(self) -> ComponentHealth:
        checked_at = utc_now()
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return ComponentHealth(
                component="postgresql", status="passing", details={}, checked_at=checked_at
            )
        except Exception as exc:  # pragma: no cover - depends on external infra
            return ComponentHealth(
                component="postgresql",
                status="failing",
                details={"error": str(exc)},
                checked_at=checked_at,
            )

    async def _check_redis(self) -> ComponentHealth:
        checked_at = utc_now()
        try:
            redis = Redis.from_url(self.settings.redis_url)
            ping_result = redis.ping()
            if isawaitable(ping_result):
                await ping_result
            await redis.aclose()
            return ComponentHealth(
                component="redis", status="passing", details={}, checked_at=checked_at
            )
        except Exception as exc:  # pragma: no cover - depends on external infra
            return ComponentHealth(
                component="redis",
                status="failing",
                details={"error": str(exc)},
                checked_at=checked_at,
            )

    def _check_kafka_state(self) -> ComponentHealth:
        checked_at = utc_now()
        return ComponentHealth(
            component="kafka",
            status="passing",
            details={"bootstrap_servers": self.settings.kafka_bootstrap_servers},
            checked_at=checked_at,
        )

    async def _check_model_endpoint(self, url: str) -> ComponentHealth:
        checked_at = utc_now()
        try:
            async with httpx.AsyncClient(timeout=self.settings.model_timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
            return ComponentHealth(
                component=f"model:{url}",
                status="passing",
                details={"status_code": response.status_code},
                checked_at=checked_at,
            )
        except Exception as exc:
            return ComponentHealth(
                component=f"model:{url}",
                status="degraded",
                details={"error": str(exc)},
                checked_at=checked_at,
            )

    async def _check_workers(self, session: AsyncSession) -> ComponentHealth:
        checked_at = utc_now()
        threshold = checked_at - timedelta(seconds=self.settings.heartbeat_ttl_seconds * 2)
        heartbeats = (await session.execute(select(WorkerHeartbeat))).scalars().all()
        stale = [
            heartbeat.worker_name
            for heartbeat in heartbeats
            if heartbeat.last_seen_at.replace(tzinfo=checked_at.tzinfo) < threshold
        ]
        status = "passing" if heartbeats and not stale else "degraded"
        return ComponentHealth(
            component="workers",
            status=status,
            details={
                "workers": [heartbeat.worker_name for heartbeat in heartbeats],
                "stale_workers": stale,
            },
            checked_at=checked_at,
        )

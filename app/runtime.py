from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.messaging.kafka import EventPublisher, InMemoryPublisher, PublisherProtocol
from app.modules.alerting.queries import AlertQueryService
from app.modules.alerting.service import AlertingService
from app.modules.audit.queries import AuditQueryService
from app.modules.audit.service import AuditService
from app.modules.monitoring.anomaly import AnomalyDetectionService, build_default_anomaly_detectors
from app.modules.monitoring.drift import DriftDetectionService, build_default_drift_detectors
from app.modules.monitoring.health import HealthService
from app.modules.monitoring.queries import MonitoringQueryService
from app.modules.orchestration.gateway import ModelGateway
from app.modules.orchestration.queries import ExecutionQueryService
from app.modules.orchestration.service import ExecutionCommandService
from app.modules.registry.commands import RegistryCommandService
from app.modules.registry.queries import RegistryQueryService
from app.projections.projector import ProjectionService


class AppRuntime:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker = SessionLocal,
        engine_override: Any = engine,
    ) -> None:
        configure_logging()
        self.settings = settings
        self.session_factory = session_factory
        self.engine = engine_override
        self.publisher: PublisherProtocol = (
            InMemoryPublisher() if settings.app_env == "test" else EventPublisher(settings)
        )
        self.audit_service = AuditService(self.publisher)
        self.audit_queries = AuditQueryService()
        self.registry_commands = RegistryCommandService(self.publisher, self.audit_service)
        self.registry_queries = RegistryQueryService()
        self.model_gateway = ModelGateway()
        self.execution_queries = ExecutionQueryService()
        self.execution_commands = ExecutionCommandService(
            self.publisher,
            self.audit_service,
            self.model_gateway,
            self.spawn_task,
        )
        self.health_service = HealthService(settings, self.engine, self.publisher)
        self.monitoring_queries = MonitoringQueryService()
        self.alert_queries = AlertQueryService()
        self.projector = ProjectionService()
        self.anomaly_detection_service = AnomalyDetectionService(
            build_default_anomaly_detectors(
                latency_zscore=settings.latency_spike_zscore,
                cost_zscore=settings.cost_spike_zscore,
            )
        )
        self.drift_detection_service = DriftDetectionService(build_default_drift_detectors())
        self.alerting_service = AlertingService(self.publisher, settings)
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def startup(self) -> None:
        await self.publisher.start()

    async def shutdown(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self.publisher.stop()

    def spawn_task(self, coro: Any) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(lambda completed: self._background_tasks.discard(completed))
        return task


@lru_cache(maxsize=1)
def get_runtime() -> AppRuntime:
    return AppRuntime(get_settings())

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, TypeVar

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

API_MODULES = frozenset(
    {
        "registry",
        "orchestration",
        "orchestration-command",
        "orchestration-query",
        "monitoring",
        "alerting",
        "audit",
    }
)
WORKER_MODULE = "workers"
ALL_RUNTIME_MODULES = frozenset({*API_MODULES, WORKER_MODULE})
T = TypeVar("T")


class AppRuntime:
    # AppRuntime играет роль application container для конкретного процесса.
    # После перехода к микросервисной топологии он больше не обязан поднимать весь
    # dependency graph целиком: каждый API-сервис может создать только те bounded
    # context dependencies, которые реально нужны его роутерам и health-слою.
    def __init__(
        self,
        settings: Settings,
        *,
        modules: frozenset[str] | None = None,
        session_factory: async_sessionmaker = SessionLocal,
        engine_override: Any = engine,
    ) -> None:
        configure_logging()
        self.settings = settings
        self.modules = modules or ALL_RUNTIME_MODULES
        self.session_factory = session_factory
        self.engine = engine_override

        # Publisher и health остаются общими почти для любого процесса: они нужны
        # и API-сервисам, и worker-ам для записи событий и проверки зависимостей.
        self.publisher: PublisherProtocol = (
            InMemoryPublisher() if settings.app_env == "test" else EventPublisher(settings)
        )
        self.health_service = HealthService(settings, self.engine, self.publisher)

        # Эти поля инициализируются только если соответствующий bounded context
        # включен в runtime. Такой подход снижает связность сервисов и упрощает
        # дальнейший physical split по отдельным deployable units.
        self.audit_service: AuditService | None = None
        self.audit_queries: AuditQueryService | None = None
        self.registry_commands: RegistryCommandService | None = None
        self.registry_queries: RegistryQueryService | None = None
        self.model_gateway: ModelGateway | None = None
        self.execution_queries: ExecutionQueryService | None = None
        self.execution_commands: ExecutionCommandService | None = None
        self.monitoring_queries: MonitoringQueryService | None = None
        self.alert_queries: AlertQueryService | None = None
        self.projector: ProjectionService | None = None
        self.anomaly_detection_service: AnomalyDetectionService | None = None
        self.drift_detection_service: DriftDetectionService | None = None
        self.alerting_service: AlertingService | None = None

        if self._needs_audit_write_side():
            self.audit_service = AuditService(self.publisher)

        if "audit" in self.modules:
            self.audit_queries = AuditQueryService()

        if "registry" in self.modules:
            self.registry_queries = RegistryQueryService()
            self.registry_commands = RegistryCommandService(
                self.publisher,
                self._require(self.audit_service, "audit_service"),
            )

        if "orchestration" in self.modules or WORKER_MODULE in self.modules:
            self.model_gateway = ModelGateway()

        if "orchestration" in self.modules or "orchestration-query" in self.modules:
            self.execution_queries = ExecutionQueryService()

        if "orchestration" in self.modules or "orchestration-command" in self.modules:
            self.execution_commands = ExecutionCommandService(
                self.publisher,
                self._require(self.audit_service, "audit_service"),
                self.model_gateway,
                self.spawn_task,
            )

        if "monitoring" in self.modules:
            self.monitoring_queries = MonitoringQueryService()

        if "alerting" in self.modules:
            self.alert_queries = AlertQueryService()

        if WORKER_MODULE in self.modules:
            self.projector = ProjectionService()
            self.anomaly_detection_service = AnomalyDetectionService(
                build_default_anomaly_detectors(
                    latency_zscore=settings.latency_spike_zscore,
                    cost_zscore=settings.cost_spike_zscore,
                )
            )
            self.drift_detection_service = DriftDetectionService(build_default_drift_detectors())
            self.alerting_service = AlertingService(self.publisher, settings)
            self.execution_commands = ExecutionCommandService(
                self.publisher,
                self._require(self.audit_service, "audit_service"),
                self._require(self.model_gateway, "model_gateway"),
                self.spawn_task,
            )

        # Здесь хранятся detached background tasks, которые были запущены из
        # HTTP-контекста, но продолжают работать уже после возврата ответа API.
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _needs_audit_write_side(self) -> bool:
        # Audit write-side нужен только сервисам, которые сами эмитят команды и
        # обязаны формировать audit trail: registry и orchestration.
        return (
            "registry" in self.modules
            or "orchestration" in self.modules
            or "orchestration-command" in self.modules
            or WORKER_MODULE in self.modules
        )

    @staticmethod
    def _require(value: T | None, name: str) -> T:
        # Если роутер или runtime wiring попытается использовать сервис, который
        # не включен в текущий microservice runtime, лучше упасть явно и рано.
        if value is None:
            raise RuntimeError(f"Runtime service '{name}' is not enabled for this process")
        return value

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


@lru_cache(maxsize=16)
def get_runtime(
    modules: tuple[str, ...] | None = None,
    *,
    service_name: str | None = None,
) -> AppRuntime:
    # Runtime кэшируется отдельно для каждой сервисной сборки. Это позволяет
    # поднять в одном кодовом базисе несколько entrypoint-ов с разным набором
    # зависимостей, но сохранить singleton-семантику внутри процесса.
    normalized_modules = frozenset(modules or ALL_RUNTIME_MODULES)
    settings = get_settings()
    if service_name is not None:
        settings = settings.model_copy(update={"service_name": service_name})
    return AppRuntime(settings, modules=normalized_modules)

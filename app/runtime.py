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
    # AppRuntime играет роль application container для всего процесса API.
    # Здесь один раз собираются сервисы, которые затем переиспользуются всеми
    # request handlers. Это снижает связность API-слоя с деталями wiring и
    # упрощает перенос модулей в отдельные сервисы в будущем.
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker = SessionLocal,
        engine_override: Any = engine,
    ) -> None:
        # Logging must be configured before any long-lived services are created so that
        # startup diagnostics from the runtime, Kafka and workers all use one format.
        configure_logging()
        self.settings = settings
        self.session_factory = session_factory
        self.engine = engine_override

        # Tests use an in-memory publisher to keep the same application wiring without
        # requiring a real Kafka broker. Production and local dev use the real publisher.
        self.publisher: PublisherProtocol = (
            InMemoryPublisher() if settings.app_env == "test" else EventPublisher(settings)
        )

        # AppRuntime is the composition root: modules receive ready-to-use collaborators
        # and stay isolated from configuration details and object construction concerns.
        # Такой подход упрощает тестирование: модульные сервисы не знают, как
        # именно создается publisher, engine или gateway, и потому легче
        # заменяются на doubles и test fixtures.
        self.audit_service = AuditService(self.publisher)
        self.audit_queries = AuditQueryService()
        self.registry_commands = RegistryCommandService(self.publisher, self.audit_service)
        self.registry_queries = RegistryQueryService()

        # Gateway инкапсулирует вызов внешнего model/inference слоя. Runtime
        # держит его здесь как singleton процесса, чтобы orchestration-сервис
        # зависел только от интерфейса, а не от способа интеграции.
        self.model_gateway = ModelGateway()
        self.execution_queries = ExecutionQueryService()

        # ExecutionCommandService получает spawn_task, а не прямой event loop.
        # Это сознательно связывает фоновый запуск workflow с runtime-контейнером,
        # который умеет потом корректно остановить эти задачи.
        self.execution_commands = ExecutionCommandService(
            self.publisher,
            self.audit_service,
            self.model_gateway,
            self.spawn_task,
        )

        # Health и monitoring сервисы собираются на уровне runtime, потому что
        # они нужны сразу нескольким маршрутам и воркерам, а их зависимости
        # пересекают границы модулей: DB, publisher, detectors и settings.
        self.health_service = HealthService(settings, self.engine, self.publisher)
        self.monitoring_queries = MonitoringQueryService()
        self.alert_queries = AlertQueryService()

        # ProjectionService материализует read-side из event stream.
        # Он не должен создаваться заново на каждый запрос, потому что
        # projection handlers являются процессными зависимостями воркеров.
        self.projector = ProjectionService()

        # Детекторы собираются через factory-функции, чтобы набор правил можно
        # было централизованно расширять без переписывания runtime wiring.
        self.anomaly_detection_service = AnomalyDetectionService(
            build_default_anomaly_detectors(
                latency_zscore=settings.latency_spike_zscore,
                cost_zscore=settings.cost_spike_zscore,
            )
        )
        self.drift_detection_service = DriftDetectionService(build_default_drift_detectors())
        self.alerting_service = AlertingService(self.publisher, settings)

        # Здесь хранятся detached background tasks, которые были запущены из
        # HTTP-контекста, но продолжают работать уже после возврата ответа API.
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def startup(self) -> None:
        # Starting the publisher eagerly avoids paying the connection cost on the first
        # write request and makes startup problems visible during boot, not at runtime.
        await self.publisher.start()

    async def shutdown(self) -> None:
        # We cancel spawned workflow tasks first so shutdown does not leave dangling
        # coroutines that still try to publish events while transports are closing.
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self.publisher.stop()

    def spawn_task(self, coro: Any) -> asyncio.Task[None]:
        # Background execution runs detached from the HTTP request lifecycle, but we
        # still track tasks here to support graceful shutdown and avoid silent leaks.
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        # Callback удаляет завершенную задачу из внутреннего набора, чтобы
        # runtime не копил "мертвые" ссылки и набор отражал только реально
        # живущие фоновые корутины.
        task.add_done_callback(lambda completed: self._background_tasks.discard(completed))
        return task


@lru_cache(maxsize=1)
def get_runtime() -> AppRuntime:
    # Runtime кэшируется как singleton на процесс. Это важно для согласованности:
    # один publisher, один набор сервисов и единый жизненный цикл на весь API.
    # Без этого разные import path могли бы случайно создать независимые runtime
    # экземпляры с дублирующими Kafka-подключениями и несогласованным shutdown.
    return AppRuntime(get_settings())

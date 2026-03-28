from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.db.base import utc_now
from app.domain.events import EventEnvelope
from app.messaging.kafka import shutdown_consumer_tasks
from app.messaging.topics import SYSTEM_HEALTH_TOPIC
from app.runtime import get_runtime
from app.workers import build_workers

logger = get_logger(__name__)


async def heartbeat_loop(role: str) -> None:
    runtime = get_runtime()
    while True:
        await runtime.publisher.publish(
            SYSTEM_HEALTH_TOPIC,
            EventEnvelope(
                event_type="worker.heartbeat",
                correlation_id="worker-heartbeat",
                trace_id="worker-heartbeat",
                source="worker.runtime",
                entity_id=f"{runtime.settings.service_name}-{role}",
                payload={
                    "id": f"{runtime.settings.service_name}-{role}",
                    "worker_name": f"{runtime.settings.service_name}-{role}",
                    "role": role,
                    "last_seen_at": utc_now(),
                    "metadata": {"service_name": runtime.settings.service_name},
                },
                metadata={"aggregate": "worker"},
            ),
        )
        await asyncio.sleep(max(5, runtime.settings.heartbeat_ttl_seconds // 2))


async def run() -> None:
    runtime = get_runtime()
    await runtime.startup()
    workers_by_role = build_workers(
        settings=runtime.settings,
        session_factory=runtime.session_factory,
        publisher=runtime.publisher,
        projector=runtime.projector,
        anomaly_detection_service=runtime.anomaly_detection_service,
        drift_detection_service=runtime.drift_detection_service,
        alerting_service=runtime.alerting_service,
    )

    selected_roles = (
        list(workers_by_role.keys())
        if runtime.settings.worker_role == "all"
        else [runtime.settings.worker_role]
    )

    consumer_tasks: list[asyncio.Task[None]] = []
    for role in selected_roles:
        for worker in workers_by_role.get(role, []):
            consumer_tasks.append(asyncio.create_task(worker.run_forever()))
    consumer_tasks.append(asyncio.create_task(heartbeat_loop(runtime.settings.worker_role)))

    logger.info("worker.runtime.started", roles=selected_roles, task_count=len(consumer_tasks))
    try:
        await asyncio.gather(*consumer_tasks)
    finally:
        await shutdown_consumer_tasks(consumer_tasks)
        await runtime.shutdown()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

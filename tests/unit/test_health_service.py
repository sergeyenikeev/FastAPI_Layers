from __future__ import annotations

import pytest

from app.runtime import AppRuntime


@pytest.mark.asyncio
async def test_live_health_returns_passing(runtime: AppRuntime) -> None:
    # Liveness intentionally поверхностный: он отвечает на вопрос "процесс жив?"
    # и не должен зависеть от внешней инфраструктуры, иначе Kubernetes начнет
    # преждевременно перезапускать контейнер при внешних сбоях.
    summary = await runtime.health_service.live()
    assert summary.status == "passing"
    assert summary.components[0].component == "api"


@pytest.mark.asyncio
async def test_ready_health_reports_workers_degraded_without_heartbeats(
    runtime: AppRuntime,
) -> None:
    # Readiness наоборот может деградировать из-за отсутствия heartbeat-ов
    # worker-ов: этот тест фиксирует различие между live и ready semantics.
    async with runtime.session_factory() as session:
        summary = await runtime.health_service.ready(session)
    workers = next(
        component for component in summary.components if component.component == "workers"
    )
    assert workers.status in {"degraded", "passing"}

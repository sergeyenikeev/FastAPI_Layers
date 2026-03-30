from __future__ import annotations

import pytest

from app.runtime import AppRuntime


@pytest.mark.asyncio
async def test_orchestration_command_runtime_keeps_only_command_dependencies(
    test_settings,
    session_factory,
    db_engine,
) -> None:
    # Этот тест защищает service-specific split orchestration-api: command ingress
    # должен уметь принять execution.start, но не обязан поднимать query-layer и
    # execution runtime зависимости вроде ModelGateway.
    runtime = AppRuntime(
        test_settings,
        modules=frozenset({"orchestration-command"}),
        session_factory=session_factory,
        engine_override=db_engine,
    )
    await runtime.startup()
    try:
        assert runtime.execution_commands is not None
        assert runtime.execution_queries is None
        assert runtime.model_gateway is None
        assert runtime.audit_service is not None
    finally:
        await runtime.shutdown()

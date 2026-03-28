from __future__ import annotations

from typing import cast

import pytest

from app.messaging.kafka import InMemoryPublisher
from app.runtime import AppRuntime
from app.modules.registry.schemas import CreateAgentRequest


@pytest.mark.asyncio
async def test_create_agent_publishes_registry_and_audit_events(runtime: AppRuntime) -> None:
    response = await runtime.registry_commands.create_agent(
        CreateAgentRequest(name="planner-agent", owner="ops-team")
    )
    publisher = cast(InMemoryPublisher, runtime.publisher)
    assert response.event_type == "agent.created"
    assert len(publisher.events) == 2
    topics = [topic for topic, _event in publisher.events]
    assert "registry.events" in topics
    assert "audit.events" in topics

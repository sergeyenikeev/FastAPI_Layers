from __future__ import annotations

import asyncio
from typing import cast

import pytest
from httpx import AsyncClient

from app.messaging.kafka import InMemoryPublisher
from app.runtime import AppRuntime


async def apply_emitted_events(runtime: AppRuntime) -> None:
    publisher = cast(InMemoryPublisher, runtime.publisher)
    async with runtime.session_factory() as session:
        for _topic, event in publisher.events:
            await runtime.projector.apply(session, event)
        await session.commit()
    publisher.events.clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_create_and_query_flow(client: AsyncClient, runtime: AppRuntime) -> None:
    response = await client.post(
        "/api/v1/agents",
        headers={"X-API-Key": "test-key"},
        json={"name": "alpha-agent", "owner": "platform"},
    )
    assert response.status_code == 200
    await apply_emitted_events(runtime)

    list_response = await client.get("/api/v1/agents", headers={"X-API-Key": "test-key"})
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "alpha-agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execution_api_creates_run_projection(
    client: AsyncClient, runtime: AppRuntime
) -> None:
    response = await client.post(
        "/api/v1/executions",
        headers={"X-API-Key": "test-key"},
        json={
            "graph_definition_id": "graph-001",
            "input_payload": {"objective": "Summarize incident"},
        },
    )
    assert response.status_code == 200
    await asyncio.sleep(0.05)
    await apply_emitted_events(runtime)

    list_response = await client.get("/api/v1/executions", headers={"X-API-Key": "test-key"})
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execution_api_runs_langgraph_steps_in_expected_order(
    client: AsyncClient, runtime: AppRuntime
) -> None:
    response = await client.post(
        "/api/v1/executions",
        headers={"X-API-Key": "test-key"},
        json={
            "graph_definition_id": "graph-sequence",
            "input_payload": {"objective": "Validate ordered workflow execution"},
        },
    )
    assert response.status_code == 200
    execution_id = response.json()["entity_id"]

    await asyncio.sleep(0.05)
    await apply_emitted_events(runtime)

    execution_response = await client.get(
        f"/api/v1/executions/{execution_id}",
        headers={"X-API-Key": "test-key"},
    )
    assert execution_response.status_code == 200
    payload = execution_response.json()

    assert payload["status"] == "succeeded"
    assert payload["output_payload"]["tool_output"].startswith(
        "Prepared actionable execution summary"
    )
    assert payload["output_payload"]["plan"].startswith("[")
    assert [step["step_name"] for step in payload["steps"]] == [
        "planner",
        "tool_runner",
        "reviewer",
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execution_api_routes_through_validator_when_requested(
    client: AsyncClient, runtime: AppRuntime
) -> None:
    response = await client.post(
        "/api/v1/executions",
        headers={"X-API-Key": "test-key"},
        json={
            "graph_definition_id": "graph-validator-branch",
            "input_payload": {
                "objective": "Validate workflow with explicit branch",
                "require_validation": True,
            },
        },
    )
    assert response.status_code == 200
    execution_id = response.json()["entity_id"]

    await asyncio.sleep(0.05)
    await apply_emitted_events(runtime)

    execution_response = await client.get(
        f"/api/v1/executions/{execution_id}",
        headers={"X-API-Key": "test-key"},
    )
    assert execution_response.status_code == 200
    payload = execution_response.json()

    assert payload["status"] == "succeeded"
    assert payload["output_payload"]["validation_summary"].startswith(
        "Validation completed"
    )
    assert [step["step_name"] for step in payload["steps"]] == [
        "planner",
        "tool_runner",
        "validator",
        "reviewer",
    ]

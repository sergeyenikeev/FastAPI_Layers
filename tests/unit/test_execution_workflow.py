from __future__ import annotations

from typing import Any

import pytest

from app.modules.orchestration.graph import ExecutionWorkflow
from app.modules.orchestration.schemas import ModelInvocationResult


class FakeGateway:
    async def invoke(
        self,
        *,
        prompt: str,
        endpoint_url: str | None,
        provider: str | None,
        model_name: str | None,
        pricing: dict[str, Any] | None = None,
    ) -> ModelInvocationResult:
        del endpoint_url, pricing
        return ModelInvocationResult(
            content=f"processed: {prompt[:32]}",
            latency_ms=12.5,
            token_input=8,
            token_output=6,
            cost_usd=0.001,
            model_name=model_name or "test-model",
            provider=provider or "test-provider",
        )


@pytest.mark.asyncio
async def test_execution_workflow_runs_full_langgraph_chain() -> None:
    emitted_steps: list[dict[str, Any]] = []

    async def emit_step(
        step_name: str,
        agent_name: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        token_usage_total: int,
        duration_ms: float,
    ) -> None:
        emitted_steps.append(
            {
                "step_name": step_name,
                "agent_name": agent_name,
                "input_payload": input_payload,
                "output_payload": output_payload,
                "token_usage_total": token_usage_total,
                "duration_ms": duration_ms,
            }
        )

    workflow = ExecutionWorkflow(FakeGateway(), emit_step)
    result = await workflow.invoke(
        {
            "execution_run_id": "run-1",
            "graph_definition_id": "graph-1",
            "input_payload": {"objective": "Prepare execution summary"},
            "objective": "Prepare execution summary",
            "model_context": {
                "endpoint_url": None,
                "provider": "test-provider",
                "model_name": "test-model",
                "pricing": {"input_per_1k": 0.001, "output_per_1k": 0.002},
            },
        }
    )

    assert result["plan"].startswith("processed:")
    assert result["tool_output"].startswith("Prepared actionable execution summary")
    assert result["review"].startswith("processed:")
    assert result["final_output"]["plan"] == result["plan"]
    assert result["final_output"]["tool_output"] == result["tool_output"]
    assert result["final_output"]["validation_summary"] == ""

    assert [item["step_name"] for item in emitted_steps] == [
        "planner",
        "tool_runner",
        "reviewer",
    ]
    assert emitted_steps[0]["agent_name"] == "planner-agent"
    assert emitted_steps[1]["agent_name"] == "tool-runner-agent"
    assert emitted_steps[2]["agent_name"] == "reviewer-agent"


@pytest.mark.asyncio
async def test_execution_workflow_routes_through_validator_when_flag_enabled() -> None:
    emitted_steps: list[dict[str, Any]] = []

    async def emit_step(
        step_name: str,
        agent_name: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        token_usage_total: int,
        duration_ms: float,
    ) -> None:
        emitted_steps.append(
            {
                "step_name": step_name,
                "agent_name": agent_name,
                "input_payload": input_payload,
                "output_payload": output_payload,
                "token_usage_total": token_usage_total,
                "duration_ms": duration_ms,
            }
        )

    workflow = ExecutionWorkflow(FakeGateway(), emit_step)
    result = await workflow.invoke(
        {
            "execution_run_id": "run-2",
            "graph_definition_id": "graph-1",
            "input_payload": {
                "objective": "Prepare validated execution summary",
                "require_validation": True,
            },
            "objective": "Prepare validated execution summary",
            "model_context": {
                "endpoint_url": None,
                "provider": "test-provider",
                "model_name": "test-model",
            },
        }
    )

    assert result["validation_required"] is True
    assert result["validation_summary"].startswith("Validation completed")
    assert result["final_output"]["validation_summary"] == result["validation_summary"]

    assert [item["step_name"] for item in emitted_steps] == [
        "planner",
        "tool_runner",
        "validator",
        "reviewer",
    ]
    assert emitted_steps[2]["agent_name"] == "validator-agent"
    assert emitted_steps[2]["input_payload"]["validation_required"] is True

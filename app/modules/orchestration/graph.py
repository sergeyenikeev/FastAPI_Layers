from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.modules.orchestration.gateway import ModelGateway


# ExecutionState — это минимальный сериализуемый контракт между command-side
# orchestration service и LangGraph workflow. Здесь хранятся только те поля,
# которые действительно нужны шагам графа и которые безопасно переносить между
# node handlers без привязки к ORM, HTTP или Kafka transport деталям.
class ExecutionState(TypedDict, total=False):
    execution_run_id: str
    deployment_id: str | None
    graph_definition_id: str | None
    input_payload: dict[str, Any]
    objective: str
    model_context: dict[str, Any]
    validation_required: bool
    plan: str
    tool_output: str
    validation_summary: str
    review: str
    final_output: dict[str, Any]


StepEmitter = Callable[
    [str, str, dict[str, Any], dict[str, Any], int, float],
    Awaitable[None],
]


class ExecutionWorkflow:
    # Этот класс инкапсулирует сам LangGraph workflow и скрывает его от остального
    # приложения за простым методом invoke(). Сервис orchestration знает только,
    # что может передать state и получить обновленный state на выходе.
    def __init__(self, gateway: ModelGateway, step_emitter: StepEmitter) -> None:
        self.gateway = gateway
        self.step_emitter = step_emitter
        self._graph = self._build()

    def _build(self) -> Any:
        # Граф собирается один раз при создании workflow. Это важно, чтобы не
        # тратить время на повторное конструирование topology на каждый запуск.
        graph = StateGraph(ExecutionState)
        graph.add_node("planner", self._planner)
        graph.add_node("tool_runner", self._tool_runner)
        graph.add_node("validator", self._validator)
        graph.add_node("reviewer", self._reviewer)

        # Базовый маршрут всегда начинается с planner и затем идет в tool_runner.
        # После tool_runner возможна условная ветка в validator.
        graph.add_edge(START, "planner")
        graph.add_edge("planner", "tool_runner")
        graph.add_conditional_edges(
            "tool_runner",
            self._route_after_tool_runner,
            {
                "validator": "validator",
                "reviewer": "reviewer",
            },
        )
        graph.add_edge("validator", "reviewer")
        graph.add_edge("reviewer", END)
        return graph.compile()

    async def invoke(self, state: ExecutionState) -> ExecutionState:
        # Внешний контракт workflow deliberately простой: orchestration service не
        # должен знать детали внутренней маршрутизации между node handlers.
        return await self._graph.ainvoke(state)

    async def _planner(self, state: ExecutionState) -> dict[str, Any]:
        # Planner отвечает за первый интеллектуальный шаг: превратить objective
        # и входной payload в компактный исполнимый план для следующих узлов.
        started = time.perf_counter()
        objective = state.get("objective") or state.get("input_payload", {}).get(
            "objective", "unknown"
        )
        model_context = state.get("model_context", {})
        prompt = (
            "You are the planning agent. Break the objective into concise executable steps.\n"
            f"Objective: {objective}\n"
            f"Context: {state.get('input_payload', {})}"
        )
        result = await self.gateway.invoke(
            prompt=prompt,
            endpoint_url=model_context.get("endpoint_url"),
            provider=model_context.get("provider"),
            model_name=model_context.get("model_name"),
            pricing=model_context.get("pricing"),
        )
        output = {
            "plan": result.content,
            "_telemetry": result.model_dump(mode="json"),
        }
        await self.step_emitter(
            "planner",
            "planner-agent",
            {"objective": objective},
            output,
            result.token_input + result.token_output,
            (time.perf_counter() - started) * 1000,
        )
        return output

    async def _tool_runner(self, state: ExecutionState) -> dict[str, Any]:
        # Tool runner в текущей реализации симулирует прикладной этап, который
        # собирает результат внешних инструментов. Он отделен от planner/reviewer,
        # потому что обычно именно здесь концентрируются side-effectful действия.
        started = time.perf_counter()
        plan = state.get("plan", "")
        input_payload = state.get("input_payload", {})
        validation_required = bool(
            state.get("validation_required")
            or input_payload.get("require_validation")
        )
        tool_output = {
            "selected_tools": ["context-summary", "risk-scan", "cost-estimator"],
            "summary": (
                "Prepared actionable execution summary for: "
                f"{input_payload.get('objective', 'objective')}"
            ),
            "plan_excerpt": plan[:280],
            "_telemetry": {
                "content": "tool-runner-local",
                "latency_ms": (time.perf_counter() - started) * 1000,
                "token_input": 0,
                "token_output": 0,
                "cost_usd": 0.0,
                "model_name": "builtin-tooling",
                "provider": "internal",
            },
        }
        await self.step_emitter(
            "tool_runner",
            "tool-runner-agent",
            {
                "plan": plan,
                "context": input_payload,
                "validation_required": validation_required,
            },
            tool_output,
            0,
            (time.perf_counter() - started) * 1000,
        )
        return {
            "tool_output": tool_output["summary"],
            "validation_required": validation_required,
        }

    def _route_after_tool_runner(self, state: ExecutionState) -> str:
        # Маршрутизация вынесена в отдельную функцию, чтобы правила ветвления
        # можно было тестировать и развивать независимо от node implementation.
        if state.get("validation_required"):
            return "validator"
        return "reviewer"

    async def _validator(self, state: ExecutionState) -> dict[str, Any]:
        # Validator — опциональный узел для рискованных сценариев. Он не заменяет
        # reviewer, а добавляет дополнительный guard rail перед финальной сборкой ответа.
        started = time.perf_counter()
        summary = (
            "Validation completed for prepared execution summary: "
            f"{state.get('tool_output', '')[:120]}"
        )
        output = {
            "validation_summary": summary,
            "_telemetry": {
                "content": "validator-local",
                "latency_ms": (time.perf_counter() - started) * 1000,
                "token_input": 0,
                "token_output": 0,
                "cost_usd": 0.0,
                "model_name": "builtin-validator",
                "provider": "internal",
            },
        }
        await self.step_emitter(
            "validator",
            "validator-agent",
            {
                "tool_output": state.get("tool_output", ""),
                "validation_required": state.get("validation_required", False),
            },
            output,
            0,
            (time.perf_counter() - started) * 1000,
        )
        return {"validation_summary": summary}

    async def _reviewer(self, state: ExecutionState) -> dict[str, Any]:
        # Reviewer завершает workflow: сводит план, tool output и опциональный
        # validation result в финальный ответ, который потом публикуется как
        # execution.finished и попадает в read-side execution_run.output_payload.
        started = time.perf_counter()
        model_context = state.get("model_context", {})
        prompt = (
            "You are the review agent. Validate the plan and tool output, "
            "then produce the final result.\n"
            f"Plan: {state.get('plan', '')}\n"
            f"Tool output: {state.get('tool_output', '')}\n"
            f"Validation: {state.get('validation_summary', '')}\n"
            f"Input payload: {state.get('input_payload', {})}"
        )
        result = await self.gateway.invoke(
            prompt=prompt,
            endpoint_url=model_context.get("endpoint_url"),
            provider=model_context.get("provider"),
            model_name=model_context.get("model_name"),
            pricing=model_context.get("pricing"),
        )
        output = {
            "review": result.content,
            "final_output": {
                "summary": result.content,
                "plan": state.get("plan", ""),
                "tool_output": state.get("tool_output", ""),
                "validation_summary": state.get("validation_summary", ""),
            },
            "_telemetry": result.model_dump(mode="json"),
        }
        await self.step_emitter(
            "reviewer",
            "reviewer-agent",
            {
                "plan": state.get("plan", ""),
                "tool_output": state.get("tool_output", ""),
                "validation_summary": state.get("validation_summary", ""),
            },
            output,
            result.token_input + result.token_output,
            (time.perf_counter() - started) * 1000,
        )
        return output

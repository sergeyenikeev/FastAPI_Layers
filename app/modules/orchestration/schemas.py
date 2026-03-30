from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# Схемы orchestration описывают HTTP-контракты вокруг запуска выполнения и
# модель результата вызова model gateway. Они отделены от runtime state графа,
# потому что внешний API не должен зависеть от внутреннего устройства workflow.
class CreateExecutionRequest(BaseModel):
    deployment_id: str | None = Field(
        default=None,
        description="Идентификатор deployment-а, по которому нужно запустить выполнение.",
        examples=["dep-prod-billing"],
    )
    graph_definition_id: str | None = Field(
        default=None,
        description="Идентификатор graph definition для прямого запуска без ссылки на deployment.",
        examples=["graph-validator-demo"],
    )
    input_payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Основной входной payload выполнения: цель, контекст и флаги "
            "управления маршрутом."
        ),
        examples=[{"objective": "Проверить деградацию workflow", "require_validation": True}],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Служебные метаданные запуска: инициатор, тикет, внешний источник "
            "и другие атрибуты."
        ),
        examples=[{"requested_by": "platform-ops", "ticket": "INC-2091"}],
    )


class ModelInvocationResult(BaseModel):
    # Это нормализованный срез результата model gateway, который позволяет
    # workflow и monitoring-слою работать с единым форматом независимо от
    # конкретного провайдера модели.
    content: str
    latency_ms: float
    token_input: int
    token_output: int
    cost_usd: float
    model_name: str
    provider: str

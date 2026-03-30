from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# Registry request schemas описывают входные контракты command-side API.
# Они не дублируют ORM-модели и не зависят от read-model DTO, потому что
# write-path и read-path эволюционируют независимо в рамках CQRS.
class CreateAgentRequest(BaseModel):
    name: str = Field(description="Человекочитаемое имя агента.", examples=["billing-ops-agent"])
    description: str | None = Field(
        default=None, description="Описание назначения и роли агента."
    )
    owner: str | None = Field(
        default=None, description="Команда или владелец, отвечающий за агента."
    )
    tags: dict[str, Any] = Field(
        default_factory=dict,
        description="Произвольные метки для поиска, фильтрации и группировки.",
    )
    version: str = Field(default="v1", description="Начальная версия агента.")
    graph_definition_id: str | None = Field(
        default=None,
        description="Связанный graph definition, который будет использован агентом по умолчанию.",
    )
    runtime_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Конфигурация рантайма агента: флаги, лимиты и execution-параметры.",
    )


class UpdateAgentRequest(BaseModel):
    # Patch-like request: все поля опциональны, чтобы API мог поддерживать
    # частичные обновления без необходимости отправлять полное состояние сущности.
    description: str | None = Field(default=None, description="Новое описание агента.")
    owner: str | None = Field(default=None, description="Новый владелец агента.")
    status: str | None = Field(
        default=None, description="Новый статус агента, например active или archived."
    )
    tags: dict[str, Any] | None = Field(
        default=None, description="Новый набор тегов или частичное обновление тегов."
    )


class CreateModelRequest(BaseModel):
    # Модель здесь понимается как внешний или внутренний inference endpoint,
    # который затем будет использоваться deployment-ами и execution workflow.
    name: str = Field(description="Человекочитаемое имя model endpoint-а.")
    provider: str = Field(description="Провайдер модели, например openai, local, internal.")
    base_url: str = Field(description="Базовый URL endpoint-а модели.")
    auth_type: str = Field(default="bearer", description="Тип авторизации для вызова endpoint-а.")
    capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="Описание возможностей модели: streaming, function-calling, multimodal и т.п.",
    )
    version: str = Field(default="v1", description="Версия конфигурации model endpoint-а.")
    model_name: str = Field(description="Внешнее или внутреннее имя модели.")
    tokenizer_name: str | None = Field(
        default=None, description="Имя токенизатора, если оно учитывается отдельно."
    )
    context_window: int | None = Field(
        default=None, description="Максимальный размер контекстного окна модели."
    )
    pricing: dict[str, Any] = Field(
        default_factory=dict,
        description="Тарифные параметры, используемые для расчета стоимости вызовов.",
    )
    is_default: bool = Field(
        default=True, description="Признак, является ли версия моделью по умолчанию."
    )


class UpdateModelRequest(BaseModel):
    provider: str | None = Field(default=None, description="Новый провайдер модели.")
    base_url: str | None = Field(default=None, description="Новый базовый URL endpoint-а.")
    auth_type: str | None = Field(default=None, description="Новый тип авторизации endpoint-а.")
    status: str | None = Field(default=None, description="Новый статус model endpoint-а.")
    capabilities: dict[str, Any] | None = Field(
        default=None, description="Обновленный набор возможностей модели."
    )


class CreateGraphRequest(BaseModel):
    name: str = Field(description="Имя graph definition.")
    description: str | None = Field(default=None, description="Описание сценария выполнения.")
    version: str = Field(default="v1", description="Версия graph definition.")
    entrypoint: str = Field(
        default="planner", description="Стартовый узел графа выполнения."
    )
    definition: dict[str, Any] = Field(
        default_factory=dict,
        description="Структурированное описание графа, его узлов и конфигурации.",
    )


class UpdateGraphRequest(BaseModel):
    description: str | None = Field(default=None, description="Новое описание графа.")
    version: str | None = Field(default=None, description="Новая версия графа.")
    entrypoint: str | None = Field(default=None, description="Новая точка входа графа.")
    definition: dict[str, Any] | None = Field(
        default=None, description="Обновленная структура графа."
    )


class CreateDeploymentRequest(BaseModel):
    # Deployment — связующая сущность между agent version, model version и
    # environment. Поэтому ее контракт богаче: он может ссылаться как на уже
    # существующее окружение, так и на окружение, создаваемое "по пути".
    agent_version_id: str = Field(description="Идентификатор версии агента для деплоя.")
    model_version_id: str | None = Field(
        default=None, description="Идентификатор версии модели, если она используется в деплое."
    )
    environment_id: str | None = Field(
        default=None, description="Существующее окружение, если оно уже создано."
    )
    environment_name: str = Field(
        default="dev", description="Имя окружения, если оно создается или выбирается по имени."
    )
    environment_description: str | None = Field(
        default=None, description="Описание окружения для нового deployment-а."
    )
    replica_count: int = Field(default=1, ge=1)
    configuration: dict[str, Any] = Field(
        default_factory=dict,
        description="Произвольная конфигурация deployment-а: лимиты, флаги и execution-настройки.",
    )


class UpdateDeploymentRequest(BaseModel):
    status: str | None = Field(default=None, description="Новый статус deployment-а.")
    replica_count: int | None = Field(default=None, ge=1)
    configuration: dict[str, Any] | None = Field(
        default=None, description="Обновленная конфигурация deployment-а."
    )


class CreateToolRequest(BaseModel):
    # ToolDefinition хранит метаданные инструмента, а не сам исполняемый код.
    # implementation_path нужен orchestration-слою как мост к реальной интеграции.
    name: str = Field(description="Имя инструмента.")
    description: str | None = Field(default=None, description="Описание назначения инструмента.")
    schema_definition: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="schema_json",
        serialization_alias="schema_json",
        description="JSON-схема входных параметров инструмента.",
    )
    implementation_path: str = Field(
        description="Путь до реализации инструмента в кодовой базе или интеграционном слое."
    )


class UpdateToolRequest(BaseModel):
    description: str | None = Field(default=None, description="Новое описание инструмента.")
    schema_definition: dict[str, Any] | None = Field(
        default=None,
        validation_alias="schema_json",
        serialization_alias="schema_json",
        description="Обновленная схема входных параметров инструмента.",
    )
    implementation_path: str | None = Field(
        default=None, description="Новый путь до реализации инструмента."
    )


class CreateEnvironmentRequest(BaseModel):
    # Environment отделен от deployment-а, чтобы одна и та же execution-среда
    # могла переиспользоваться множеством конфигураций и аналитических отчетов.
    name: str = Field(description="Имя окружения, например dev, stage или prod.")
    description: str | None = Field(default=None, description="Описание назначения окружения.")
    labels: dict[str, Any] = Field(
        default_factory=dict,
        description="Метки окружения для поиска, правил и operational-фильтрации.",
    )


class UpdateEnvironmentRequest(BaseModel):
    description: str | None = Field(default=None, description="Новое описание окружения.")
    labels: dict[str, Any] | None = Field(
        default=None, description="Обновленный набор меток окружения."
    )

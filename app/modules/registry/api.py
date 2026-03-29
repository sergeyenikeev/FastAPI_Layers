from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, require_role
from app.db.session import get_session
from app.domain.schemas import (
    AgentDTO,
    CommandAccepted,
    DeploymentDTO,
    EnvironmentDTO,
    GraphDefinitionDTO,
    ModelEndpointDTO,
    Page,
    ToolDefinitionDTO,
)
from app.modules.registry.commands import RegistryCommandService
from app.modules.registry.queries import RegistryQueryService
from app.modules.registry.schemas import (
    CreateAgentRequest,
    CreateDeploymentRequest,
    CreateEnvironmentRequest,
    CreateGraphRequest,
    CreateModelRequest,
    CreateToolRequest,
    UpdateAgentRequest,
    UpdateDeploymentRequest,
    UpdateEnvironmentRequest,
    UpdateGraphRequest,
    UpdateModelRequest,
    UpdateToolRequest,
)

router = APIRouter(prefix="", tags=["registry"])


def get_registry_commands() -> RegistryCommandService:
    from app.runtime import get_runtime

    return get_runtime().registry_commands


def get_registry_queries() -> RegistryQueryService:
    from app.runtime import get_runtime

    return get_runtime().registry_queries


@router.post(
    "/agents",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Создать агента и его стартовую версию",
    description=(
        "Создает нового агента в registry-контуре и публикует событие `agent.created`. "
        "Ручка нужна для регистрации новой исполняемой сущности платформы до ее "
        "дальнейшего деплоя и запуска."
    ),
)
async def create_agent(
    payload: CreateAgentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_agent(payload)


@router.get(
    "/agents",
    response_model=Page[AgentDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список агентов",
    description=(
        "Возвращает пагинированный список агентов из read model. "
        "Ручка нужна для просмотра каталога зарегистрированных агентов, "
        "поиска по имени и навигации по доступным версиям."
    ),
)
async def list_agents(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(default=None, description="Поисковая строка по имени и описанию."),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[AgentDTO]:
    return await service.list_agents(session, page=page, page_size=page_size, q=q)


@router.get(
    "/agents/{agent_id}",
    response_model=AgentDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку агента",
    description=(
        "Возвращает одного агента по идентификатору из materialized read model. "
        "Ручка нужна для просмотра детальной конфигурации агента и его связей "
        "с версиями и графами выполнения."
    ),
)
async def get_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> AgentDTO:
    return await service.get_agent(session, agent_id)


@router.put(
    "/agents/{agent_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить агента",
    description=(
        "Обновляет метаданные агента и публикует событие `agent.updated`. "
        "Ручка нужна для изменения описания, статуса и других атрибутов без "
        "прямого редактирования read-side таблиц."
    ),
)
async def update_agent(
    agent_id: str,
    payload: UpdateAgentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_agent(agent_id, payload)


@router.delete(
    "/agents/{agent_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить агента",
    description=(
        "Удаляет агента через командный контур и публикует событие `agent.deleted`. "
        "Ручка нужна для административной очистки реестра и вывода сущности "
        "из дальнейшего использования."
    ),
)
async def delete_agent(
    agent_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_agent(agent_id)


@router.post(
    "/models",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Зарегистрировать endpoint модели и версию модели",
    description=(
        "Создает запись о model endpoint и его версии в registry-контуре. "
        "Ручка нужна, чтобы orchestration-слой мог использовать внешний "
        "или внутренний inference endpoint с контролируемой конфигурацией."
    ),
)
async def create_model(
    payload: CreateModelRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_model(payload)


@router.get(
    "/models",
    response_model=Page[ModelEndpointDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список моделей",
    description=(
        "Возвращает пагинированный список зарегистрированных model endpoint-ов и их версий. "
        "Ручка нужна для выбора модели при конфигурировании deployment-ов и "
        "для эксплуатационного обзора доступного inference-слоя."
    ),
)
async def list_models(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(default=None, description="Поисковая строка по модели или провайдеру."),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[ModelEndpointDTO]:
    return await service.list_models(session, page=page, page_size=page_size, q=q)


@router.get(
    "/models/{model_id}",
    response_model=ModelEndpointDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку модели",
    description=(
        "Возвращает детальную карточку model endpoint по идентификатору. "
        "Ручка нужна для просмотра провайдера, URL, версии, параметров "
        "тарификации и другой конфигурации модели."
    ),
)
async def get_model(
    model_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> ModelEndpointDTO:
    return await service.get_model(session, model_id)


@router.put(
    "/models/{model_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить модель",
    description=(
        "Обновляет конфигурацию model endpoint и публикует событие `model.updated`. "
        "Ручка нужна для смены параметров подключения, метаданных или "
        "операционных настроек без ручного редактирования БД."
    ),
)
async def update_model(
    model_id: str,
    payload: UpdateModelRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_model(model_id, payload)


@router.delete(
    "/models/{model_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить модель",
    description=(
        "Удаляет модель из registry-контура и публикует событие `model.deleted`. "
        "Ручка нужна для деактивации или полного удаления более не используемых "
        "model endpoint-ов."
    ),
)
async def delete_model(
    model_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_model(model_id)


@router.post(
    "/graphs",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Создать определение графа выполнения",
    description=(
        "Создает GraphDefinition и публикует событие `graph.created`. "
        "Ручка нужна для регистрации логического workflow, который затем "
        "может быть привязан к версии агента или deployment-у."
    ),
)
async def create_graph(
    payload: CreateGraphRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_graph(payload)


@router.get(
    "/graphs",
    response_model=Page[GraphDefinitionDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список графов выполнения",
    description=(
        "Возвращает пагинированный список зарегистрированных graph definition-ов. "
        "Ручка нужна для выбора сценария выполнения и обзора доступных workflow."
    ),
)
async def list_graphs(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(default=None, description="Поисковая строка по графам выполнения."),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[GraphDefinitionDTO]:
    return await service.list_graphs(session, page=page, page_size=page_size, q=q)


@router.get(
    "/graphs/{graph_id}",
    response_model=GraphDefinitionDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку графа выполнения",
    description=(
        "Возвращает один graph definition по идентификатору. "
        "Ручка нужна для просмотра версии сценария, его описания и связанной "
        "конфигурации orchestration-контура."
    ),
)
async def get_graph(
    graph_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> GraphDefinitionDTO:
    return await service.get_graph(session, graph_id)


@router.put(
    "/graphs/{graph_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить граф выполнения",
    description=(
        "Обновляет определение графа и публикует событие `graph.updated`. "
        "Ручка нужна для эволюции сценариев выполнения без обхода event-driven контура."
    ),
)
async def update_graph(
    graph_id: str,
    payload: UpdateGraphRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_graph(graph_id, payload)


@router.delete(
    "/graphs/{graph_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить граф выполнения",
    description=(
        "Удаляет graph definition и публикует событие `graph.deleted`. "
        "Ручка нужна для административного вывода устаревших сценариев из эксплуатации."
    ),
)
async def delete_graph(
    graph_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_graph(graph_id)


@router.post(
    "/deployments",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Создать deployment",
    description=(
        "Создает deployment, связывающий агента, граф, модель и окружение. "
        "Ручка нужна для подготовки исполняемой конфигурации, по которой затем "
        "можно запускать execution run."
    ),
)
async def create_deployment(
    payload: CreateDeploymentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_deployment(payload)


@router.get(
    "/deployments",
    response_model=Page[DeploymentDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список deployment-ов",
    description=(
        "Возвращает пагинированный список deployment-ов из read model. "
        "Ручка нужна для обзора доступных конфигураций запуска и контроля "
        "их текущего состояния."
    ),
)
async def list_deployments(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(
        default=None, description="Поиск по deployment-ам и связанным сущностям."
    ),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[DeploymentDTO]:
    return await service.list_deployments(session, page=page, page_size=page_size, q=q)


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку deployment-а",
    description=(
        "Возвращает один deployment по идентификатору. "
        "Ручка нужна для просмотра того, какой агент, граф, модель и окружение "
        "связаны в конкретной исполняемой конфигурации."
    ),
)
async def get_deployment(
    deployment_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> DeploymentDTO:
    return await service.get_deployment(session, deployment_id)


@router.put(
    "/deployments/{deployment_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить deployment",
    description=(
        "Обновляет deployment и публикует событие `deployment.updated`. "
        "Ручка нужна для смены конфигурации выполнения без прямого вмешательства "
        "в проекции и read-side таблицы."
    ),
)
async def update_deployment(
    deployment_id: str,
    payload: UpdateDeploymentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_deployment(deployment_id, payload)


@router.delete(
    "/deployments/{deployment_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить deployment",
    description=(
        "Удаляет deployment и публикует событие `deployment.deleted`. "
        "Ручка нужна для вывода исполняемой конфигурации из эксплуатации."
    ),
)
async def delete_deployment(
    deployment_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_deployment(deployment_id)


@router.post(
    "/tools",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Зарегистрировать инструмент",
    description=(
        "Создает ToolDefinition в registry-контуре. "
        "Ручка нужна для учета и версионирования инструментов, которые могут "
        "использоваться в сценариях выполнения."
    ),
)
async def create_tool(
    payload: CreateToolRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_tool(payload)


@router.get(
    "/tools",
    response_model=Page[ToolDefinitionDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список инструментов",
    description=(
        "Возвращает список зарегистрированных инструментов. "
        "Ручка нужна для навигации по доступным tool definition-ам и их параметрам."
    ),
)
async def list_tools(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(default=None, description="Поисковая строка по инструментам."),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[ToolDefinitionDTO]:
    return await service.list_tools(session, page=page, page_size=page_size, q=q)


@router.get(
    "/tools/{tool_id}",
    response_model=ToolDefinitionDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку инструмента",
    description=(
        "Возвращает один ToolDefinition по идентификатору. "
        "Ручка нужна для просмотра конфигурации конкретного инструмента."
    ),
)
async def get_tool(
    tool_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> ToolDefinitionDTO:
    return await service.get_tool(session, tool_id)


@router.put(
    "/tools/{tool_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить инструмент",
    description=(
        "Обновляет описание или конфигурацию инструмента. "
        "Ручка нужна для сопровождения registry-описания tools через event-driven write-path."
    ),
)
async def update_tool(
    tool_id: str,
    payload: UpdateToolRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_tool(tool_id, payload)


@router.delete(
    "/tools/{tool_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить инструмент",
    description=(
        "Удаляет инструмент из registry-контура. "
        "Ручка нужна для административного удаления устаревших или запрещенных tools."
    ),
)
async def delete_tool(
    tool_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_tool(tool_id)


@router.post(
    "/environments",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Создать окружение",
    description=(
        "Создает Environment в registry-контуре. "
        "Ручка нужна для описания dev, stage, prod и других сред, к которым затем "
        "привязываются deployment-ы и стоимость выполнения."
    ),
)
async def create_environment(
    payload: CreateEnvironmentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_environment(payload)


@router.get(
    "/environments",
    response_model=Page[EnvironmentDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список окружений",
    description=(
        "Возвращает список окружений платформы. "
        "Ручка нужна для просмотра доступных execution-сред и фильтрации deployment-ов по ним."
    ),
)
async def list_environments(
    page: int = Query(default=1, ge=1, description="Номер страницы результата."),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы."),
    q: str | None = Query(default=None, description="Поисковая строка по окружениям."),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[EnvironmentDTO]:
    return await service.list_environments(session, page=page, page_size=page_size, q=q)


@router.get(
    "/environments/{environment_id}",
    response_model=EnvironmentDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить карточку окружения",
    description=(
        "Возвращает одно окружение по идентификатору. "
        "Ручка нужна для просмотра детальной конфигурации среды выполнения."
    ),
)
async def get_environment(
    environment_id: str,
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> EnvironmentDTO:
    return await service.get_environment(session, environment_id)


@router.put(
    "/environments/{environment_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Обновить окружение",
    description=(
        "Обновляет свойства окружения и публикует событие `environment.updated`. "
        "Ручка нужна для сопровождения execution-сред через единый write-path."
    ),
)
async def update_environment(
    environment_id: str,
    payload: UpdateEnvironmentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.update_environment(environment_id, payload)


@router.delete(
    "/environments/{environment_id}",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="Удалить окружение",
    description=(
        "Удаляет окружение из registry-контура. "
        "Ручка нужна для административной очистки и вывода среды из использования."
    ),
)
async def delete_environment(
    environment_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_environment(environment_id)

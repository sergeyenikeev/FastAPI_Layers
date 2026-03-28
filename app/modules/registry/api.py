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
    "/agents", response_model=CommandAccepted, dependencies=[Depends(require_role(Role.OPERATOR))]
)
async def create_agent(
    payload: CreateAgentRequest,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.create_agent(payload)


@router.get(
    "/agents", response_model=Page[AgentDTO], dependencies=[Depends(require_role(Role.VIEWER))]
)
async def list_agents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[AgentDTO]:
    return await service.list_agents(session, page=page, page_size=page_size, q=q)


@router.get(
    "/agents/{agent_id}", response_model=AgentDTO, dependencies=[Depends(require_role(Role.VIEWER))]
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
)
async def delete_agent(
    agent_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_agent(agent_id)


@router.post(
    "/models", response_model=CommandAccepted, dependencies=[Depends(require_role(Role.OPERATOR))]
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
)
async def list_models(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[ModelEndpointDTO]:
    return await service.list_models(session, page=page, page_size=page_size, q=q)


@router.get(
    "/models/{model_id}",
    response_model=ModelEndpointDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
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
)
async def delete_model(
    model_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_model(model_id)


@router.post(
    "/graphs", response_model=CommandAccepted, dependencies=[Depends(require_role(Role.OPERATOR))]
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
)
async def list_graphs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[GraphDefinitionDTO]:
    return await service.list_graphs(session, page=page, page_size=page_size, q=q)


@router.get(
    "/graphs/{graph_id}",
    response_model=GraphDefinitionDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
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
)
async def list_deployments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[DeploymentDTO]:
    return await service.list_deployments(session, page=page, page_size=page_size, q=q)


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
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
)
async def delete_deployment(
    deployment_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_deployment(deployment_id)


@router.post(
    "/tools", response_model=CommandAccepted, dependencies=[Depends(require_role(Role.OPERATOR))]
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
)
async def list_tools(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[ToolDefinitionDTO]:
    return await service.list_tools(session, page=page, page_size=page_size, q=q)


@router.get(
    "/tools/{tool_id}",
    response_model=ToolDefinitionDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
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
)
async def list_environments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: RegistryQueryService = Depends(get_registry_queries),
) -> Page[EnvironmentDTO]:
    return await service.list_environments(session, page=page, page_size=page_size, q=q)


@router.get(
    "/environments/{environment_id}",
    response_model=EnvironmentDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
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
)
async def delete_environment(
    environment_id: str,
    service: RegistryCommandService = Depends(get_registry_commands),
) -> CommandAccepted:
    return await service.delete_environment(environment_id)

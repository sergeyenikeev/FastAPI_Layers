from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models import (
    Agent,
    Deployment,
    Environment,
    GraphDefinition,
    ModelEndpoint,
    ToolDefinition,
)
from app.db.repositories import paginate_query
from app.domain.schemas import (
    AgentDTO,
    DeploymentDTO,
    EnvironmentDTO,
    GraphDefinitionDTO,
    ModelEndpointDTO,
    Page,
    ToolDefinitionDTO,
)


class RegistryQueryService:
    async def list_agents(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[AgentDTO]:
        query = select(Agent).order_by(Agent.created_at.desc())
        if q:
            query = query.where(or_(Agent.name.ilike(f"%{q}%"), Agent.owner.ilike(f"%{q}%")))
        items, total = await paginate_query(session, query, page, page_size)
        return Page[AgentDTO](
            items=[AgentDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_agent(self, session: AsyncSession, agent_id: str) -> AgentDTO:
        entity = await session.get(Agent, agent_id)
        if entity is None:
            raise DomainError("Agent not found", code="not_found", extra={"agent_id": agent_id})
        return AgentDTO.model_validate(entity)

    async def list_models(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[ModelEndpointDTO]:
        query = select(ModelEndpoint).order_by(ModelEndpoint.created_at.desc())
        if q:
            query = query.where(
                or_(
                    ModelEndpoint.name.ilike(f"%{q}%"),
                    ModelEndpoint.provider.ilike(f"%{q}%"),
                )
            )
        items, total = await paginate_query(session, query, page, page_size)
        return Page[ModelEndpointDTO](
            items=[ModelEndpointDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_model(self, session: AsyncSession, model_id: str) -> ModelEndpointDTO:
        entity = await session.get(ModelEndpoint, model_id)
        if entity is None:
            raise DomainError(
                "Model endpoint not found", code="not_found", extra={"model_id": model_id}
            )
        return ModelEndpointDTO.model_validate(entity)

    async def list_graphs(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[GraphDefinitionDTO]:
        query = select(GraphDefinition).order_by(GraphDefinition.created_at.desc())
        if q:
            query = query.where(GraphDefinition.name.ilike(f"%{q}%"))
        items, total = await paginate_query(session, query, page, page_size)
        return Page[GraphDefinitionDTO](
            items=[GraphDefinitionDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_graph(self, session: AsyncSession, graph_id: str) -> GraphDefinitionDTO:
        entity = await session.get(GraphDefinition, graph_id)
        if entity is None:
            raise DomainError(
                "Graph definition not found", code="not_found", extra={"graph_id": graph_id}
            )
        return GraphDefinitionDTO.model_validate(entity)

    async def list_deployments(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[DeploymentDTO]:
        query = select(Deployment).order_by(Deployment.created_at.desc())
        if q:
            environment_ids = select(Environment.id).where(Environment.name.ilike(f"%{q}%"))
            query = query.where(
                or_(
                    Deployment.status.ilike(f"%{q}%"),
                    Deployment.environment_id.in_(environment_ids),
                )
            )
        items, total = await paginate_query(session, query, page, page_size)
        return Page[DeploymentDTO](
            items=[DeploymentDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_deployment(self, session: AsyncSession, deployment_id: str) -> DeploymentDTO:
        entity = await session.get(Deployment, deployment_id)
        if entity is None:
            raise DomainError(
                "Deployment not found",
                code="not_found",
                extra={"deployment_id": deployment_id},
            )
        return DeploymentDTO.model_validate(entity)

    async def list_tools(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[ToolDefinitionDTO]:
        query = select(ToolDefinition).order_by(ToolDefinition.created_at.desc())
        if q:
            query = query.where(ToolDefinition.name.ilike(f"%{q}%"))
        items, total = await paginate_query(session, query, page, page_size)
        return Page[ToolDefinitionDTO](
            items=[ToolDefinitionDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_tool(self, session: AsyncSession, tool_id: str) -> ToolDefinitionDTO:
        entity = await session.get(ToolDefinition, tool_id)
        if entity is None:
            raise DomainError(
                "Tool definition not found", code="not_found", extra={"tool_id": tool_id}
            )
        return ToolDefinitionDTO.model_validate(entity)

    async def list_environments(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
    ) -> Page[EnvironmentDTO]:
        query = select(Environment).order_by(Environment.created_at.desc())
        if q:
            query = query.where(Environment.name.ilike(f"%{q}%"))
        items, total = await paginate_query(session, query, page, page_size)
        return Page[EnvironmentDTO](
            items=[EnvironmentDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_environment(self, session: AsyncSession, environment_id: str) -> EnvironmentDTO:
        entity = await session.get(Environment, environment_id)
        if entity is None:
            raise DomainError(
                "Environment not found",
                code="not_found",
                extra={"environment_id": environment_id},
            )
        return EnvironmentDTO.model_validate(entity)

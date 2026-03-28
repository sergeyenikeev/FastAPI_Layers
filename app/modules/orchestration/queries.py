from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import ExecutionRun
from app.db.repositories import paginate_query
from app.domain.schemas import ExecutionRunDTO, ExecutionStepDTO, Page


class ExecutionQueryService:
    async def list_executions(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        deployment_id: str | None = None,
        status: str | None = None,
    ) -> Page[ExecutionRunDTO]:
        query = (
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.steps))
            .order_by(ExecutionRun.started_at.desc())
        )
        if deployment_id:
            query = query.where(ExecutionRun.deployment_id == deployment_id)
        if status:
            query = query.where(ExecutionRun.status == status)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[ExecutionRunDTO](
            items=[self._to_dto(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_execution(self, session: AsyncSession, execution_id: str) -> ExecutionRunDTO:
        query = (
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.steps))
            .where(ExecutionRun.id == execution_id)
        )
        entity = (await session.execute(query)).scalar_one_or_none()
        if entity is None:
            raise DomainError(
                "Execution run not found",
                code="not_found",
                extra={"execution_id": execution_id},
            )
        return self._to_dto(entity)

    def _to_dto(self, entity: ExecutionRun) -> ExecutionRunDTO:
        payload = ExecutionRunDTO.model_validate(entity).model_dump(exclude={"steps"})
        return ExecutionRunDTO(
            **payload,
            steps=[ExecutionStepDTO.model_validate(step) for step in entity.steps],
        )

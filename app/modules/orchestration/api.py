from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, require_role
from app.db.session import get_session
from app.domain.schemas import CommandAccepted, ExecutionRunDTO, Page
from app.modules.orchestration.queries import ExecutionQueryService
from app.modules.orchestration.schemas import CreateExecutionRequest
from app.modules.orchestration.service import ExecutionCommandService

router = APIRouter(prefix="", tags=["orchestration"])


def get_execution_commands() -> ExecutionCommandService:
    from app.runtime import get_runtime

    return get_runtime().execution_commands


def get_execution_queries() -> ExecutionQueryService:
    from app.runtime import get_runtime

    return get_runtime().execution_queries


@router.post(
    "/executions",
    response_model=CommandAccepted,
    dependencies=[Depends(require_role(Role.OPERATOR))],
    summary="Запустить выполнение сценария",
    description=(
        "Создает новый execution run и публикует событие `execution.started`. "
        "Ручка нужна для асинхронного запуска сценария по deployment-у или graph definition. "
        "HTTP-запрос только принимает команду, а само выполнение продолжается в фоне."
    ),
)
async def create_execution(
    payload: CreateExecutionRequest,
    session: AsyncSession = Depends(get_session),
    service: ExecutionCommandService = Depends(get_execution_commands),
) -> CommandAccepted:
    return await service.create_execution(session, payload)


@router.get(
    "/executions",
    response_model=Page[ExecutionRunDTO],
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить список выполнений",
    description=(
        "Возвращает пагинированный список execution run из read model с фильтрацией "
        "по deployment и статусу. Ручка нужна для операционного обзора текущих и "
        "завершенных запусков."
    ),
)
async def list_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    deployment_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: ExecutionQueryService = Depends(get_execution_queries),
) -> Page[ExecutionRunDTO]:
    return await service.list_executions(
        session,
        page=page,
        page_size=page_size,
        deployment_id=deployment_id,
        status=status,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionRunDTO,
    dependencies=[Depends(require_role(Role.VIEWER))],
    summary="Получить детали выполнения",
    description=(
        "Возвращает execution run вместе с материализованными шагами выполнения. "
        "Ручка нужна для разбора конкретного запуска, его результата, статуса, "
        "ошибки и step-by-step истории."
    ),
)
async def get_execution(
    execution_id: str,
    session: AsyncSession = Depends(get_session),
    service: ExecutionQueryService = Depends(get_execution_queries),
) -> ExecutionRunDTO:
    return await service.get_execution(session, execution_id)

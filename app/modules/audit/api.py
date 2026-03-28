from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, require_role
from app.db.session import get_session
from app.domain.schemas import AuditEventDTO, Page
from app.modules.audit.queries import AuditQueryService

router = APIRouter(prefix="", tags=["audit"])


def get_audit_queries() -> AuditQueryService:
    from app.runtime import get_runtime

    return get_runtime().audit_queries


@router.get(
    "/audit", response_model=Page[AuditEventDTO], dependencies=[Depends(require_role(Role.VIEWER))]
)
async def list_audit_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    entity_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    service: AuditQueryService = Depends(get_audit_queries),
) -> Page[AuditEventDTO]:
    return await service.list_audit_events(
        session,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
    )

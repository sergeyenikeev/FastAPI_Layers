from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent
from app.db.repositories import paginate_query
from app.domain.schemas import AuditEventDTO, Page


class AuditQueryService:
    # Audit query service отдает paginated view исторического журнала действий.
    async def list_audit_events(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        entity_type: str | None = None,
    ) -> Page[AuditEventDTO]:
        query = select(AuditEvent).order_by(AuditEvent.created_at.desc())
        if entity_type:
            query = query.where(AuditEvent.entity_type == entity_type)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[AuditEventDTO](
            items=[AuditEventDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

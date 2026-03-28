from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert
from app.db.repositories import paginate_query
from app.domain.schemas import AlertDTO, Page


class AlertQueryService:
    async def list_alerts(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        severity: str | None = None,
        status: str | None = None,
    ) -> Page[AlertDTO]:
        query = select(Alert).order_by(Alert.created_at.desc())
        if severity:
            query = query.where(Alert.severity == severity)
        if status:
            query = query.where(Alert.status == status)
        items, total = await paginate_query(session, query, page, page_size)
        return Page[AlertDTO](
            items=[AlertDTO.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

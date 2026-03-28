from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate_query(
    session: AsyncSession,
    query: Select[Any],
    page: int,
    page_size: int,
) -> tuple[Sequence[Any], int]:
    total_query = select(func.count()).select_from(query.subquery())
    total = int((await session.execute(total_query)).scalar_one())
    paged = query.limit(page_size).offset((page - 1) * page_size)
    items = (await session.execute(paged)).scalars().all()
    return items, total

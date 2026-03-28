from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import Environment
from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(Environment).where(Environment.id == "env-dev"))
        ).scalar_one_or_none()
        if existing is None:
            session.add(Environment(id="env-dev", name="dev", description="Local development"))
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())

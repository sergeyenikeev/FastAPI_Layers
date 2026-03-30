from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import Environment
from app.db.session import SessionLocal


async def main() -> None:
    # Исторически это был самый простой bootstrap локального окружения до
    # появления более богатого dev_stack.py. Скрипт оставлен как минимальный
    # fallback: если нужна только базовая запись env-dev в БД, он делает это
    # идемпотентно и без поднятия полного demo-контура.
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(Environment).where(Environment.id == "env-dev"))
        ).scalar_one_or_none()
        if existing is None:
            # Скрипт не пытается синхронизировать полный registry, а создает
            # только самый базовый development environment для локальных сценариев.
            session.add(Environment(id="env-dev", name="dev", description="Local development"))
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())

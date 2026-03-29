from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    # Единая функция времени упрощает согласованную работу с timezone-aware
    # timestamp-ами в ORM, projections и доменных событиях.
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # Базовый declarative class хранит общий type annotation map, чтобы dict-поля
    # в ORM автоматически маппились в JSON и не повторялись в каждой модели.
    type_annotation_map = {
        dict[str, Any]: JSON,
    }


class UUIDPrimaryKeyMixin:
    # UUIDPrimaryKeyMixin дает единый способ создавать string UUID primary key
    # во всех сущностях платформы, включая domain read models и инфраструктуру.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))


class TimestampMixin:
    # TimestampMixin обеспечивает стандартный набор created_at/updated_at для
    # тех таблиц, где важна auditability и наблюдаемость изменений состояния.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

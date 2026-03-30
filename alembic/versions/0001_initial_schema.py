"""Initial schema for workflow operations platform."""

from __future__ import annotations

import app.db.models  # noqa: F401
from alembic import op
from app.db.base import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Первая ревизия специально использует текущее состояние Base.metadata как
    # "bootstrap snapshot" схемы. Для стартового репозитория это снижает риск
    # рассинхронизации между ORM и миграцией до появления последующих ревизий.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Обратная миграция зеркалирует bootstrap-логику: для самой первой ревизии
    # допустимо снести всю схему целиком, потому что более раннего состояния нет.
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

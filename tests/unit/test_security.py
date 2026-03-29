from __future__ import annotations

import jwt
import pytest
from fastapi import HTTPException
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.core.security import Role, get_auth_context, require_role


@pytest.mark.asyncio
async def test_api_key_auth_accepts_known_key(monkeypatch: MonkeyPatch) -> None:
    # API key должен давать локальному операторскому сценарию валидный auth context.
    monkeypatch.setattr(
        "app.core.security.get_settings",
        lambda: get_settings().model_copy(update={"api_keys": ["known-key"]}),
    )
    context = await get_auth_context(api_key="known-key", credentials=None)
    assert context.role == Role.ADMIN


@pytest.mark.asyncio
async def test_jwt_auth_decodes_role(monkeypatch: MonkeyPatch) -> None:
    # JWT-путь отдельно проверяет, что роль и subject действительно достаются из token claims.
    settings = get_settings().model_copy(
        update={
            "jwt_secret": "test-secret-key-with-32-bytes-minimum",
            "jwt_algorithm": "HS256",
        }
    )
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    token = jwt.encode(
        {"sub": "alice", "role": "operator"}, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    context = await get_auth_context(
        api_key=None, credentials=type("Creds", (), {"credentials": token})()
    )
    assert context.subject == "alice"
    assert context.role == Role.OPERATOR


@pytest.mark.asyncio
async def test_require_role_rejects_lower_privilege() -> None:
    # Guard against regression: dependency обязана закрывать доступ роли ниже требуемой.
    dependency = require_role(Role.ADMIN)
    with pytest.raises(HTTPException):
        await dependency(type("Ctx", (), {"role": Role.VIEWER})())

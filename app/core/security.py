from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.context import set_principal_id

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class AuthContext(BaseModel):
    subject: str
    role: Role
    auth_type: str
    claims: dict[str, Any] = {}


ROLE_ORDER: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
}


def _decode_jwt(token: str) -> AuthContext:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    role = Role(payload.get("role", Role.VIEWER))
    return AuthContext(
        subject=str(payload.get("sub", "jwt-user")),
        role=role,
        auth_type="jwt",
        claims=payload,
    )


async def get_auth_context(
    api_key: Annotated[str | None, Security(api_key_header)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> AuthContext:
    settings = get_settings()
    if api_key:
        if api_key not in settings.api_keys:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        context = AuthContext(subject="api-key-user", role=Role.ADMIN, auth_type="api_key")
        set_principal_id(context.subject)
        return context

    if credentials:
        try:
            context = _decode_jwt(credentials.credentials)
        except jwt.PyJWTError as exc:  # pragma: no cover - library exception variants
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            ) from exc
        set_principal_id(context.subject)
        return context

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


def require_role(required_role: Role) -> Callable[[AuthContext], Awaitable[AuthContext]]:
    async def _dependency(
        context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if ROLE_ORDER[context.role] < ROLE_ORDER[required_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return context

    return _dependency

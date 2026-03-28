from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: str
    extra: dict[str, Any] | None = None


class DomainError(Exception):
    def __init__(
        self, detail: str, code: str = "domain_error", extra: dict[str, Any] | None = None
    ):
        self.detail = detail
        self.code = code
        self.extra = extra or {}
        super().__init__(detail)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(detail=exc.detail, code=exc.code, extra=exc.extra).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(detail=str(exc), code="value_error").model_dump(),
        )

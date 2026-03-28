from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import build_api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import CorrelationMiddleware, RateLimitStubMiddleware
from app.core.observability import setup_telemetry
from app.db.session import engine
from app.runtime import get_runtime


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = get_runtime()
    await runtime.startup()
    yield
    await runtime.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Workflow Operations Platform",
        version="0.1.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimitStubMiddleware)
    install_error_handlers(app)
    setup_telemetry(app, engine, settings)
    app.include_router(build_api_router(), prefix=settings.api_v1_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    return app


app = create_app()

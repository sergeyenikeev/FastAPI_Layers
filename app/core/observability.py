from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

_instrumented_fastapi_apps: set[int] = set()
_sqlalchemy_instrumented = False


def setup_telemetry(app: FastAPI, engine: AsyncEngine, settings: Settings) -> None:
    global _sqlalchemy_instrumented
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    with suppress(Exception):
        trace.set_tracer_provider(provider)

    app_id = id(app)
    if app_id not in _instrumented_fastapi_apps:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        _instrumented_fastapi_apps.add(app_id)
    if not _sqlalchemy_instrumented:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)
        _sqlalchemy_instrumented = True


@asynccontextmanager
async def span(name: str) -> AsyncIterator[None]:
    tracer = trace.get_tracer("workflow-platform")
    with tracer.start_as_current_span(name):
        yield

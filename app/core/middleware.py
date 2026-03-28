from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.context import ensure_correlation_id, set_trace_id
from app.core.logging import get_logger
from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY

logger = get_logger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = ensure_correlation_id(request.headers.get("X-Correlation-Id"))
        trace_id = set_trace_id(request.headers.get("X-Trace-Id") or str(uuid4()))
        start = time.perf_counter()

        response = await call_next(request)
        elapsed = time.perf_counter() - start

        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(elapsed)
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Trace-Id"] = trace_id

        logger.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=elapsed,
        )
        return response


class RateLimitStubMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-RateLimit-Policy"] = "stub"
        return response

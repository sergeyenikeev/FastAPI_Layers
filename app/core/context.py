from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
principal_id_ctx: ContextVar[str] = ContextVar("principal_id", default="anonymous")


def ensure_correlation_id(value: str | None = None) -> str:
    correlation_id = value or str(uuid4())
    correlation_id_ctx.set(correlation_id)
    return correlation_id


def set_trace_id(value: str | None) -> str:
    trace_id = value or str(uuid4())
    trace_id_ctx.set(trace_id)
    return trace_id


def set_principal_id(value: str) -> None:
    principal_id_ctx.set(value)


def get_correlation_id() -> str:
    return correlation_id_ctx.get() or ensure_correlation_id()


def get_trace_id() -> str:
    return trace_id_ctx.get() or set_trace_id(None)


def get_principal_id() -> str:
    return principal_id_ctx.get()

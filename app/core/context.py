from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

# ContextVar-ы используются как process-local request context для correlation,
# tracing и principal identity. Это позволяет прокидывать контекст сквозь
# async-await без явной передачи этих значений по каждой функции.
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
principal_id_ctx: ContextVar[str] = ContextVar("principal_id", default="anonymous")


def ensure_correlation_id(value: str | None = None) -> str:
    # Если correlation_id уже пришел извне, мы его переиспользуем; иначе
    # генерируем новый. Так сохраняется трассировка между внешними системами.
    correlation_id = value or str(uuid4())
    correlation_id_ctx.set(correlation_id)
    return correlation_id


def set_trace_id(value: str | None) -> str:
    # Trace id ведется отдельно от correlation id, потому что correlation нужен
    # бизнес-потоку в целом, а trace чаще относится к наблюдаемому execution path.
    trace_id = value or str(uuid4())
    trace_id_ctx.set(trace_id)
    return trace_id


def set_principal_id(value: str) -> None:
    principal_id_ctx.set(value)


def get_correlation_id() -> str:
    # Getter гарантирует, что даже в глубоком слое без middleware-контекста
    # приложение все равно получит валидный correlation identifier.
    return correlation_id_ctx.get() or ensure_correlation_id()


def get_trace_id() -> str:
    return trace_id_ctx.get() or set_trace_id(None)


def get_principal_id() -> str:
    return principal_id_ctx.get()

from __future__ import annotations

from fastapi import Request

from app.runtime import AppRuntime


def get_request_runtime(request: Request) -> AppRuntime:
    # Для микросервисной сборки runtime хранится в app.state конкретного FastAPI
    # приложения. Фолбэк на get_runtime() оставлен для обратной совместимости:
    # старые тесты и legacy entrypoint все еще могут жить на process-wide singleton.
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        return runtime
    from app.runtime import get_runtime

    return get_runtime()

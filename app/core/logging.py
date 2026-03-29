from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.context import get_correlation_id, get_principal_id, get_trace_id


def _inject_context(
    _logger: structlog.stdlib.BoundLogger, _method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    # Логгер автоматически обогащается текущими correlation/trace/principal id,
    # чтобы любой лог можно было связать с запросом, событием и пользователем.
    event_dict.setdefault("correlation_id", get_correlation_id())
    event_dict.setdefault("trace_id", get_trace_id())
    event_dict.setdefault("principal_id", get_principal_id())
    return event_dict


def configure_logging() -> None:
    # Проект использует structlog в JSON-режиме, потому что такие логи легче
    # агрегировать в Kubernetes и связывать с tracing/alerting системами.
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.dict_tracebacks,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(message)s",
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    # Обертка сохраняет единый способ получать логгер и не размазывать по коду
    # прямую зависимость от деталей structlog configuration.
    return structlog.get_logger(name)

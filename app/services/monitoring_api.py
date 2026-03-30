from __future__ import annotations

from app.app_factory import create_service_app
from app.core.config import get_settings
from app.runtime import get_runtime

settings = get_settings().model_copy(update={"service_name": "monitoring-api"})
app = create_service_app(
    title="Workflow Monitoring Service",
    description=(
        "Микросервис мониторинга. Отдает health checks, performance metrics, cost, "
        "anomaly и drift read models."
    ),
    settings=settings,
    runtime=get_runtime(),
    modules=["monitoring"],
)

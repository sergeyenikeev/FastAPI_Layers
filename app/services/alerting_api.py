from __future__ import annotations

from app.app_factory import create_service_app
from app.core.config import get_settings
from app.runtime import get_runtime

settings = get_settings().model_copy(update={"service_name": "alerting-api"})
app = create_service_app(
    title="Workflow Alerting Service",
    description="Микросервис просмотра и эксплуатации alert-сущностей платформы.",
    settings=settings,
    runtime=get_runtime(modules=("alerting",), service_name="alerting-api"),
    modules=["alerting"],
)

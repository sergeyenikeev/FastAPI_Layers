from __future__ import annotations

from app.app_factory import create_service_app
from app.core.config import get_settings
from app.runtime import get_runtime

settings = get_settings().model_copy(update={"service_name": "registry-api"})
app = create_service_app(
    title="Workflow Registry Service",
    description=(
        "Микросервис реестра. Отвечает за command-side и read-side API для агентов, "
        "моделей, графов, deployment-ов, инструментов и окружений."
    ),
    settings=settings,
    runtime=get_runtime(modules=("registry",), service_name="registry-api"),
    modules=["registry"],
)

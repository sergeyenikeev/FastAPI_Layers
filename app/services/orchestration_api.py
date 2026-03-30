from __future__ import annotations

from app.app_factory import create_service_app
from app.core.config import get_settings
from app.runtime import get_runtime

settings = get_settings().model_copy(update={"service_name": "orchestration-api"})
app = create_service_app(
    title="Workflow Orchestration Service",
    description=(
        "Микросервис command ingress для оркестрации. Принимает команды на запуск "
        "execution run и публикует стартовые события в Kafka."
    ),
    settings=settings,
    runtime=get_runtime(
        modules=("orchestration-command",), service_name="orchestration-api"
    ),
    modules=["orchestration-command"],
)

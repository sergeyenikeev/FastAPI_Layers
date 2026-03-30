from __future__ import annotations

from app.app_factory import create_service_app
from app.core.config import get_settings
from app.runtime import get_runtime

settings = get_settings().model_copy(update={"service_name": "orchestration-api"})
app = create_service_app(
    title="Workflow Orchestration Service",
    description=(
        "Микросервис оркестрации. Принимает команды на запуск execution run и "
        "отдает материализованное состояние выполнений."
    ),
    settings=settings,
    runtime=get_runtime(modules=("orchestration",), service_name="orchestration-api"),
    modules=["orchestration"],
)

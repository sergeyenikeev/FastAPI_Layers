OPENAPI_TAGS: dict[str, dict[str, str]] = {
    "registry": {
        "name": "registry",
        "description": (
            "Группа ручек для управления реестровыми сущностями платформы. "
            "Здесь создаются и изменяются агенты, модели, графы, деплойменты, "
            "инструменты и окружения."
        ),
    },
    "orchestration": {
        "name": "orchestration",
        "description": (
            "Группа ручек для запуска и просмотра выполнений. Через эти endpoint-ы "
            "создаются execution run и читается их материализованное состояние."
        ),
    },
    "monitoring": {
        "name": "monitoring",
        "description": (
            "Группа ручек для health checks, метрик, стоимости, anomaly и drift "
            "report-ов, используемых в эксплуатации платформы."
        ),
    },
    "alerting": {
        "name": "alerting",
        "description": (
            "Группа ручек для просмотра алертов, сгенерированных аналитическим и "
            "операционным контуром платформы."
        ),
    },
    "audit": {
        "name": "audit",
        "description": (
            "Группа ручек для просмотра аудиторского следа, correlation_id, "
            "trace_id и истории изменений."
        ),
    },
}

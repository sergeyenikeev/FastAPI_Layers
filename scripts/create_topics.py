from __future__ import annotations

import asyncio

from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from app.core.config import get_settings
from app.messaging.topics import TOPIC_TO_DLQ

# Скрипт создает минимальный topic landscape для локального или тестового Kafka.
# Это operational utility, а не часть runtime: приложение умеет работать и с
# уже существующим кластером, но локальному стеку полезно уметь самобутстрапиться.
BASE_TOPICS = [
    "registry.events",
    "agent.executions",
    "agent.steps",
    "system.metrics",
    "system.health",
    "model.inference",
    "cost.events",
    "anomaly.events",
    "drift.events",
    "alerts.events",
    "audit.events",
]


async def main() -> None:
    # Настройки берутся из того же config-слоя, что и у приложения, чтобы
    # bootstrap использовал те же bootstrap servers и client-id conventions.
    settings = get_settings()
    client = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-admin",
    )
    await client.start()
    try:
        existing = set(await client.list_topics())
        # Для каждого бизнес-topic заранее резервируется DLQ-топик, чтобы
        # локальная среда повторяла production-подход к retry/failure handling.
        desired = BASE_TOPICS + list(TOPIC_TO_DLQ.values())
        topics = [
            NewTopic(name=topic, num_partitions=3, replication_factor=1)
            for topic in desired
            if topic not in existing
        ]
        if topics:
            # Скрипт идемпотентен: создаются только отсутствующие topics, так
            # что его можно безопасно запускать повторно при пересборке стека.
            await client.create_topics(topics)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

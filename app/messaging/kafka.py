from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from typing import Any, Protocol

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import ConsumerRecord, OffsetAndMetadata
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.metrics import KAFKA_CONSUMER_LAG
from app.core.observability import span
from app.db.models import ProcessedEvent
from app.domain.events import DeadLetterEnvelope, EventEnvelope
from app.messaging.topics import TOPIC_TO_DLQ

logger = get_logger(__name__)


def serialize_event(event: EventEnvelope) -> bytes:
    # Все события сериализуются из единого EventEnvelope, чтобы producer и
    # consumer слой не расходились по wire format между модулями.
    return orjson.dumps(event.model_dump(mode="json"))


def deserialize_event(value: bytes) -> EventEnvelope:
    # Десериализация симметрична serialize_event и сразу валидирует payload
    # через Pydantic-модель envelope, а не через разрозненные dict access.
    return EventEnvelope.model_validate(orjson.loads(value))


def default_partition_key(event: EventEnvelope) -> bytes:
    # We prefer stable business identifiers so logically related records land in the
    # same partition and preserve order for a given execution/model/agent stream.
    for key_name in ("agent_id", "model_id", "deployment_id", "execution_run_id"):
        if key_name in event.payload and event.payload[key_name]:
            return str(event.payload[key_name]).encode()
    return event.entity_id.encode()


class EventPublisher:
    # Producer оборачивает aiokafka и задает единые правила публикации событий:
    # idempotent producer, JSON envelope, tracing headers и stable partition key.
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=self.settings.kafka_client_id,
            security_protocol=self.settings.kafka_security_protocol,
            request_timeout_ms=self.settings.kafka_request_timeout_ms,
            enable_idempotence=self.settings.kafka_enable_idempotence,
            value_serializer=lambda value: value,
            key_serializer=lambda value: value,
        )
        await self._producer.start()
        logger.info(
            "kafka.producer.started", bootstrap_servers=self.settings.kafka_bootstrap_servers
        )

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        logger.info("kafka.producer.stopped")
        self._producer = None

    async def publish(
        self,
        topic: str,
        event: EventEnvelope,
        key: bytes | None = None,
        headers: Sequence[tuple[str, bytes]] | None = None,
    ) -> None:
        if self._producer is None:
            await self.start()
        assert self._producer is not None

        # Kafka headers duplicate key tracing fields so operators can inspect messages
        # and route them without deserializing the full JSON envelope.
        with_headers = list(headers or [])
        with_headers.extend(
            [
                ("event_type", event.event_type.encode()),
                ("event_id", event.event_id.encode()),
                ("correlation_id", event.correlation_id.encode()),
                ("trace_id", event.trace_id.encode()),
            ]
        )

        async with span(f"kafka.publish.{topic}"):
            await self._producer.send_and_wait(
                topic,
                serialize_event(event),
                key=key or default_partition_key(event),
                headers=with_headers,
            )
        logger.info(
            "kafka.event.published",
            topic=topic,
            event_type=event.event_type,
            event_id=event.event_id,
            entity_id=event.entity_id,
        )


class EventHandler(Protocol):
    # Handler protocol фиксирует контракт для worker-обработчиков: они получают
    # уже десериализованный event, сырую Kafka record и открытую DB session.
    async def __call__(
        self,
        event: EventEnvelope,
        record: Any,
        session: AsyncSession,
    ) -> None: ...


class PublisherProtocol(Protocol):
    # Протокол позволяет runtime и сервисам зависеть от абстракции publisher,
    # а не от конкретного Kafka implementation. Это упрощает тесты и local fakes.
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(
        self,
        topic: str,
        event: EventEnvelope,
        key: bytes | None = None,
        headers: Sequence[tuple[str, bytes]] | None = None,
    ) -> None: ...


class BaseConsumerWorker:
    # BaseConsumerWorker реализует общий шаблон Kafka consumer-а:
    # polling, tracing, manual commit, idempotency, retries и DLQ.
    # Конкретная бизнес-логика остается в injected handler.
    def __init__(
        self,
        *,
        name: str,
        group_id: str,
        topics: Sequence[str],
        handler: EventHandler,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: PublisherProtocol,
        settings: Settings | None = None,
        max_retries: int = 3,
    ) -> None:
        self.name = name
        self.group_id = group_id
        self.topics = list(topics)
        self.handler = handler
        self.session_factory = session_factory
        self.publisher = publisher
        self.settings = settings or get_settings()
        self.max_retries = max_retries
        self._consumer: AIOKafkaConsumer | None = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        if self._consumer is not None:
            return
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=f"{self.settings.kafka_client_id}-{self.name}",
            group_id=self.group_id,
            security_protocol=self.settings.kafka_security_protocol,
            enable_auto_commit=False,
            auto_offset_reset="latest",
        )
        await self.publisher.start()
        await self._consumer.start()
        logger.info(
            "kafka.consumer.started", worker=self.name, group_id=self.group_id, topics=self.topics
        )

    async def stop(self) -> None:
        # Shutdown signal хранится отдельно от stop() consumer-а, чтобы loop в
        # run_forever мог корректно завершиться даже между polling итерациями.
        self._shutdown.set()
        if self._consumer is not None:
            await self._consumer.stop()
            logger.info("kafka.consumer.stopped", worker=self.name)
            self._consumer = None

    async def run_forever(self) -> None:
        await self.start()
        assert self._consumer is not None
        try:
            while not self._shutdown.is_set():
                # getmany gives us a bounded batch and lets the loop periodically wake up
                # to observe shutdown signals instead of blocking indefinitely on consume.
                result = await self._consumer.getmany(timeout_ms=1000, max_records=100)
                for tp, records in result.items():
                    for record in records:
                        await self._process_record(record)
                    # Lag is tracked after each batch so autoscaling and dashboards can
                    # show how far a consumer group is behind in near real time.
                    highwater = self._consumer.highwater(tp) or 0
                    position = await self._consumer.position(tp)
                    KAFKA_CONSUMER_LAG.labels(self.group_id, tp.topic).set(
                        max(highwater - position, 0)
                    )
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()

    async def _process_record(self, record: ConsumerRecord) -> None:
        # Весь record processing завязан на at-least-once delivery: сначала
        # side effects + processed marker в транзакции, потом offset commit.
        event = deserialize_event(record.value)
        for attempt in range(1, self.max_retries + 1):
            try:
                async with span(f"kafka.consume.{record.topic}"), self.session_factory() as session:
                    # Idempotency is enforced per consumer group. This lets multiple
                    # independent consumers react to one event while still protecting
                    # each concrete read model or analytics pipeline from duplicates.
                    if await self._is_processed(session, event.event_id):
                        await session.rollback()
                        await self._commit(record)
                        logger.info(
                            "kafka.event.skipped_idempotent",
                            worker=self.name,
                            event_id=event.event_id,
                            topic=record.topic,
                        )
                        return

                    await self.handler(event, record, session)
                    # The processed marker is stored in the same transaction as the
                    # handler side effects so duplicates cannot partially reapply state.
                    session.add(
                        ProcessedEvent(
                            consumer_group=self.group_id,
                            event_id=event.event_id,
                            topic=record.topic,
                            partition=record.partition,
                            offset=record.offset,
                        )
                    )
                    await session.commit()

                await self._commit(record)
                return
            except Exception as exc:  # pragma: no cover - exercised via unit tests with fakes
                logger.exception(
                    "kafka.event.processing_failed",
                    worker=self.name,
                    topic=record.topic,
                    event_id=event.event_id,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt >= self.max_retries:
                    # After the retry budget is exhausted we commit the source offset and
                    # move the message to DLQ so one poisonous event does not block the
                    # entire partition forever.
                    await self._publish_dlq(record.topic, event, str(exc), retry_count=attempt)
                    await self._commit(record)
                    return

    async def _is_processed(self, session: AsyncSession, event_id: str) -> bool:
        query = select(ProcessedEvent).where(
            ProcessedEvent.consumer_group == self.group_id,
            ProcessedEvent.event_id == event_id,
        )
        return (await session.execute(query)).scalar_one_or_none() is not None

    async def _commit(self, record: ConsumerRecord) -> None:
        assert self._consumer is not None
        tp = record.topic, record.partition
        assignment = list(self._consumer.assignment())
        for topic_partition in assignment:
            if topic_partition.topic == tp[0] and topic_partition.partition == tp[1]:
                # Manual offset commit happens only after successful processing or DLQ
                # transfer. That keeps at-least-once delivery while limiting duplicates.
                await self._consumer.commit(
                    {topic_partition: OffsetAndMetadata(record.offset + 1, "")}
                )
                return

    async def _publish_dlq(
        self,
        topic: str,
        event: EventEnvelope,
        error: str,
        retry_count: int,
    ) -> None:
        dlq_topic = TOPIC_TO_DLQ[topic]
        # DLQ keeps the original event intact and wraps failure metadata around it so
        # operators can inspect, replay or compensate without losing the source payload.
        envelope = DeadLetterEnvelope(
            topic=topic,
            consumer_group=self.group_id,
            retry_count=retry_count,
            error=error,
            original_event=event,
        )
        await self.publisher.publish(
            dlq_topic,
            EventEnvelope(
                event_type=f"{event.event_type}.dlq",
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                source=self.name,
                entity_id=event.entity_id,
                payload=envelope.model_dump(mode="json"),
                metadata={"dlq_topic": dlq_topic},
            ),
        )


class InMemoryPublisher:
    # InMemoryPublisher нужен для тестов и локальных unit-scenarios, где важно
    # сохранить тот же publisher contract, но не поднимать реальный Kafka broker.
    def __init__(self) -> None:
        self.events: list[tuple[str, EventEnvelope]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(
        self,
        topic: str,
        event: EventEnvelope,
        key: bytes | None = None,
        headers: Sequence[tuple[str, bytes]] | None = None,
    ) -> None:
        del key, headers
        self.events.append((topic, event))


async def shutdown_consumer_tasks(tasks: Sequence[asyncio.Task[None]]) -> None:
    # Функция выделена отдельно, чтобы worker runtime использовал единый и
    # предсказуемый способ остановки consumer tasks при graceful shutdown.
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task

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
    return orjson.dumps(event.model_dump(mode="json"))


def deserialize_event(value: bytes) -> EventEnvelope:
    return EventEnvelope.model_validate(orjson.loads(value))


def default_partition_key(event: EventEnvelope) -> bytes:
    for key_name in ("agent_id", "model_id", "deployment_id", "execution_run_id"):
        if key_name in event.payload and event.payload[key_name]:
            return str(event.payload[key_name]).encode()
    return event.entity_id.encode()


class EventPublisher:
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
    async def __call__(
        self,
        event: EventEnvelope,
        record: Any,
        session: AsyncSession,
    ) -> None: ...


class PublisherProtocol(Protocol):
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
                result = await self._consumer.getmany(timeout_ms=1000, max_records=100)
                for tp, records in result.items():
                    for record in records:
                        await self._process_record(record)
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
        event = deserialize_event(record.value)
        for attempt in range(1, self.max_retries + 1):
            try:
                async with span(f"kafka.consume.{record.topic}"):
                    async with self.session_factory() as session:
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
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task

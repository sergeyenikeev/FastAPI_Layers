# Kafka: топики и схема работы

## Стратегия партиционирования

- События, связанные с агентами, партиционируются по `agent_id`, когда он доступен
- События, связанные с моделями, партиционируются по `model_id` или `model_name`
- Для сценариев выполнения без явного ключа используется `entity_id`

Это сохраняет порядок событий внутри агрегата и одновременно позволяет горизонтально масштабировать потребителей.

## Группы потребителей

- `projection-consumers`
- `metrics-aggregation-consumers`
- `anomaly-consumers`
- `drift-consumers`
- `alert-consumers`

## Локальная диагностика Kafka

Для локальной разработки и разбора инцидентов используйте готовый отладочный скрипт:

```bash
uv run python scripts/kafka_debug.py all
```

Он работает через `docker compose exec` внутри Kafka-контейнера и позволяет:

- вывести список топиков;
- вывести список consumer groups;
- посмотреть lag всех consumer groups;
- быстро найти DLQ-топики;
- описать конкретный topic или group.

Базовые команды:

- `uv run python scripts/kafka_debug.py topics`
- `uv run python scripts/kafka_debug.py groups`
- `uv run python scripts/kafka_debug.py lag`
- `uv run python scripts/kafka_debug.py dlq`
- `uv run python scripts/kafka_debug.py describe-group projection-consumers`
- `uv run python scripts/kafka_debug.py peek-topic agent.executions --max-messages 1 --from-beginning`
- `uv run python scripts/kafka_debug.py peek-dlq agent.executions.dlq --max-messages 1 --from-beginning`

## Обработка сбоев

- Идемпотентность на стороне потребителя обеспечивается таблицей `processed_events`
- Ручной commit offset выполняется только после успешной обработки или отправки сообщения в DLQ
- Неуспешные сообщения повторно обрабатываются внутри процесса, а затем перенаправляются в `.dlq`

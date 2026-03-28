# Поток событий

## Топики Kafka

- `registry.events`
- `agent.executions`
- `agent.steps`
- `system.metrics`
- `system.health`
- `model.inference`
- `cost.events`
- `anomaly.events`
- `drift.events`
- `alerts.events`
- `audit.events`

Для каждого топика предусмотрен соответствующий `.dlq`-топик для маршрутизации сообщений, которые не удалось обработать после исчерпания политики повторов.

## Конверт события

Каждое событие соответствует единой схеме:

- `event_id`
- `event_version`
- `event_type`
- `timestamp`
- `correlation_id`
- `trace_id`
- `source`
- `entity_id`
- `payload`
- `metadata`

## Основные потоки

### Реестр

1. `POST /api/v1/agents`
2. API публикует `agent.created` в `registry.events`
3. Потребитель проекций выполняет upsert в `agents` и `agent_versions`
4. API чтения отдает данные из PostgreSQL

### Выполнение

1. `POST /api/v1/executions`
2. API публикует `execution.started`
3. Сценарий выполняет цепочку `planner -> tool_runner -> reviewer`
4. Каждый шаг публикует `step.completed`
5. Сценарий завершает поток событием `execution.finished` или `execution.failed`
6. Потребитель проекций записывает `execution_runs` и `execution_steps`

### Аналитика

1. `system.metrics` и `cost.events` поступают в воркеры аномалий
2. `model.inference` вместе с метриками моделей поступают в воркеры дрейфа
3. `anomaly.events` и `drift.events` поступают в воркеры алертинга
4. `alerts.events` материализуют алерты и запускают заглушки уведомлений

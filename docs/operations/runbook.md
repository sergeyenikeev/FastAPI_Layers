# Операционный регламент

## Локальный bootstrap для диагностики

Если нужно быстро поднять воспроизводимое локальное окружение для диагностики:

1. Выполните `uv run python scripts/dev_stack.py start`
2. Дождитесь проверки `/api/v1/health/ready`
3. Проверьте результат smoke-сценария
4. При повторном запуске без пересборки используйте `uv run python scripts/dev_stack.py start --no-build`
5. Для отдельной перепроверки API используйте `uv run python scripts/dev_stack.py smoke`
6. Для остановки окружения используйте `uv run python scripts/dev_stack.py stop`

## API не готово к работе

1. Проверьте `/api/v1/health/ready`
2. Убедитесь в доступности PostgreSQL, Redis и Kafka
3. Проверьте сигналы heartbeat рабочих процессов в таблице `worker_heartbeats`

## Растет очередь в Kafka

1. Проверьте количество реплик воркеров, масштабируемых через KEDA
2. Проверьте offsets consumer groups и рост DLQ
3. Масштабируйте аналитические или projection-воркеры, если отставание локализовано
4. Для локальной диагностики используйте `uv run python scripts/kafka_debug.py lag`
5. Для точечной проверки используйте `uv run python scripts/kafka_debug.py describe-group projection-consumers`

## Сообщения ушли в DLQ

1. Выполните `uv run python scripts/kafka_debug.py dlq`
2. Если нужен контекст по конкретному topic, выполните `uv run python scripts/kafka_debug.py describe-topic agent.executions.dlq`
3. Чтобы увидеть само сообщение, выполните `uv run python scripts/kafka_debug.py peek-dlq agent.executions.dlq --max-messages 1 --from-beginning`
4. Сопоставьте рост DLQ с логами соответствующего worker-процесса
5. Проверьте, не изменился ли event payload без синхронного обновления projection или consumer handler

## Шторм алертов по дрейфу

1. Проверьте `drift_reports` и последние метрики токенов модели
2. Подтвердите изменение входного распределения на входящей стороне
3. Меняйте пороги у детекторов только после подтверждения, что это новая норма, а не инцидент

## Всплеск стоимости

1. Проверьте `/api/v1/costs`
2. Сопоставьте рост с последними `execution_runs` и событиями `model.inference`
3. Проверьте, не вызваны ли всплески токенов ретраями или разрастанием запроса к модели

## Проверка ветки validator

Если нужно убедиться, что условная ветка `validator` работает в окружении корректно:

1. Отправьте тестовый запуск через `POST /api/v1/executions` с `input_payload.require_validation=true`
2. Убедитесь, что в `agent.steps` появился шаг `validator`
3. Проверьте, что итоговое событие `execution.finished` содержит `output_payload.validation_summary`
4. Убедитесь, что `GET /api/v1/executions/{id}` возвращает порядок шагов `planner -> tool_runner -> validator -> reviewer`
5. Если шаг не появился, проверьте payload входного события и логи orchestration-сервиса

Минимальный пример запроса:

```json
{
  "graph_definition_id": "graph-validator-demo",
  "input_payload": {
    "objective": "Validate rollout plan for a degraded workflow",
    "require_validation": true
  }
}
```

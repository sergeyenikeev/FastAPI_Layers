# Операционный регламент

## API не готово к работе

1. Проверьте `/api/v1/health/ready`
2. Убедитесь в доступности PostgreSQL, Redis и Kafka
3. Проверьте сигналы heartbeat рабочих процессов в таблице `worker_heartbeats`

## Растет очередь в Kafka

1. Проверьте количество реплик воркеров, масштабируемых через KEDA
2. Проверьте offsets consumer groups и рост DLQ
3. Масштабируйте аналитические или projection-воркеры, если отставание локализовано

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

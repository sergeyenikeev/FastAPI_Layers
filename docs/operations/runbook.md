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

## Поднят не тот API-сервис

Если контейнер стартует, но отвечает “не тем” Swagger, не тем набором ручек или не тем `service.name`, проверяйте цепочку запуска сверху вниз:

1. Убедитесь, что в контейнере задан правильный `APP_COMPONENT`
2. Проверьте, что `docker/start-api.sh` маппит это значение на ожидаемый модуль
3. Проверьте, что `SERVICE_NAME` соответствует сервису, который вы ожидаете увидеть в логах и трассах
4. Если это Kubernetes, проверьте соответствующий `Deployment` и его env-переменные
5. Если это локальный Docker, проверьте блок сервиса в `docker-compose.yml`

Практическая матрица:

- `gateway` -> `app.main:app`
- `registry` -> `app.services.registry_api:app`
- `orchestration` -> `app.services.orchestration_api:app`
- `monitoring` -> `app.services.monitoring_api:app`
- `alerting` -> `app.services.alerting_api:app`
- `audit` -> `app.services.audit_api:app`

Симптомы проблемы обычно выглядят так:

- на `/docs` открыт не тот bounded context;
- в логах приходит неожиданный `service_name`;
- Prometheus видит метрики не у того job;
- трассы OpenTelemetry помечаются другим `service.name`, чем ожидалось.

Минимальный порядок проверки:

1. `docker compose logs -f <service-name>`
2. `docker compose exec <service-name> printenv APP_COMPONENT`
3. `docker compose exec <service-name> printenv SERVICE_NAME`
4. открыть `/` и `/docs` у этого сервиса

Если проблема в Kubernetes:

1. `kubectl get deployment -n <namespace>`
2. `kubectl describe deployment <name> -n <namespace>`
3. проверить env `APP_COMPONENT` и `SERVICE_NAME`
4. проверить, что pod labels и service selector совпадают

## Сервис не виден в Prometheus

Если сервис работает, но его нет в Prometheus:

1. Убедитесь, что сам сервис отвечает на `/metrics`
2. Проверьте, что Prometheus scrapes именно этот target
3. В Kubernetes проверьте наличие `ServiceMonitor`
4. Проверьте labels `component` и selector у `Service`
5. Убедитесь, что `service_name` и `job_name` не перепутаны в ожиданиях

Локально:

1. Откройте `http://localhost:9090/targets`
2. Найдите нужный target:
   - `workflow-gateway`
   - `workflow-registry`
   - `workflow-orchestration`
   - `workflow-monitoring`
   - `workflow-alerting`
   - `workflow-audit`
3. Если target down, проверьте:
   - контейнер сервиса запущен ли;
   - отвечает ли `/metrics`;
   - нет ли ошибки в `docker/prometheus.yml`

В Kubernetes:

1. Проверьте `ServiceMonitor`
2. Проверьте labels на `Service`
3. Проверьте, что Prometheus Operator видит этот `ServiceMonitor`
4. Если `NetworkPolicy` включена, убедитесь, что namespace Prometheus разрешен

## Сервис не виден в OpenTelemetry

Если HTTP работает, но трассы по сервису не приходят:

1. Проверьте `OTEL_EXPORTER_OTLP_ENDPOINT`
2. Проверьте `SERVICE_NAME`
3. Проверьте доступность `otel-collector`
4. Проверьте логи collector

Локально:

1. `docker compose logs -f otel-collector`
2. Убедитесь, что API-сервису задан `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
3. Сделайте запрос к сервису и проверьте, что collector печатает trace через `debug` exporter

В Kubernetes:

1. Проверьте endpoint OTLP в `ConfigMap` и env контейнера
2. Проверьте DNS и сетевую доступность collector-сервиса
3. Убедитесь, что `service.name` в trace соответствует `SERVICE_NAME` процесса

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

## Нужно найти конкретное событие выполнения

1. Если известен `correlation_id`, выполните `uv run python scripts/kafka_debug.py peek-topic agent.executions --from-beginning --correlation-id <correlation_id>`
2. Если известен `execution_run_id`, выполните `uv run python scripts/kafka_debug.py peek-topic agent.executions --from-beginning --payload-field execution_run.id=<execution_id>`
3. Для финального события используйте `uv run python scripts/kafka_debug.py peek-topic agent.executions --from-beginning --event-type execution.finished`
4. Для шагов используйте аналогичный поиск в `agent.steps` по `--payload-field execution_step.execution_run_id=<execution_id>`

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

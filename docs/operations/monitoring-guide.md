# Руководство по мониторингу

## Источники сигналов

- HTTP-метрики и метрики выполнения через Prometheus `/metrics`
- Трассы через OpenTelemetry OTLP exporter
- JSON-журналы с `correlation_id`, `trace_id` и `principal_id`

## Ключевые метрики

- `workflow_platform_http_requests_total`
- `workflow_platform_http_request_duration_seconds`
- `workflow_platform_execution_step_duration_seconds`
- `workflow_platform_kafka_consumer_lag`
- `workflow_platform_active_executions`
- `workflow_platform_compute_cost_usd_total`

## API чтения

- `/api/v1/metrics`
- `/api/v1/metrics/summary`
- `/api/v1/costs`
- `/api/v1/anomalies`
- `/api/v1/drift`
- `/api/v1/alerts`

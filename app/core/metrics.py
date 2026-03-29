from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Здесь объявлены process-wide Prometheus метрики runtime-слоя. Они являются
# техническими метриками процесса и не заменяют event/materialized metrics,
# которые платформа дополнительно хранит в собственной read model.
REQUEST_COUNT = Counter(
    "workflow_platform_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "workflow_platform_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
EXECUTION_STEP_DURATION = Histogram(
    "workflow_platform_execution_step_duration_seconds",
    "Duration of execution steps",
    ["agent_name", "step_name", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
KAFKA_CONSUMER_LAG = Gauge(
    "workflow_platform_kafka_consumer_lag",
    "Estimated Kafka consumer lag by group and topic",
    ["consumer_group", "topic"],
)
ACTIVE_EXECUTIONS = Gauge(
    "workflow_platform_active_executions",
    "Number of currently active executions",
)
COMPUTE_CALL_COST = Counter(
    "workflow_platform_compute_cost_usd_total",
    "Accumulated compute spend in USD",
    ["agent_id", "workflow_id", "environment"],
)

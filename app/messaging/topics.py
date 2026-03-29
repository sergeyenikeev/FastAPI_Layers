from __future__ import annotations

# Topics и их DLQ собраны в одном модуле, чтобы publisher, workers, Helm values
# и документация опирались на единый source of truth для event backbone.
AGENT_EXECUTIONS_TOPIC = "agent.executions"
AGENT_EXECUTION_DLQ_TOPIC = "agent.executions.dlq"
AGENT_STEPS_TOPIC = "agent.steps"
AGENT_STEPS_DLQ_TOPIC = "agent.steps.dlq"
SYSTEM_METRICS_TOPIC = "system.metrics"
SYSTEM_METRICS_DLQ_TOPIC = "system.metrics.dlq"
SYSTEM_HEALTH_TOPIC = "system.health"
SYSTEM_HEALTH_DLQ_TOPIC = "system.health.dlq"
MODEL_INFERENCE_TOPIC = "model.inference"
MODEL_INFERENCE_DLQ_TOPIC = "model.inference.dlq"
COST_EVENTS_TOPIC = "cost.events"
COST_EVENTS_DLQ_TOPIC = "cost.events.dlq"
ANOMALY_EVENTS_TOPIC = "anomaly.events"
ANOMALY_EVENTS_DLQ_TOPIC = "anomaly.events.dlq"
DRIFT_EVENTS_TOPIC = "drift.events"
DRIFT_EVENTS_DLQ_TOPIC = "drift.events.dlq"
ALERTS_EVENTS_TOPIC = "alerts.events"
ALERTS_EVENTS_DLQ_TOPIC = "alerts.events.dlq"
AUDIT_EVENTS_TOPIC = "audit.events"
AUDIT_EVENTS_DLQ_TOPIC = "audit.events.dlq"
REGISTRY_EVENTS_TOPIC = "registry.events"
REGISTRY_EVENTS_DLQ_TOPIC = "registry.events.dlq"

TOPIC_TO_DLQ = {
    AGENT_EXECUTIONS_TOPIC: AGENT_EXECUTION_DLQ_TOPIC,
    AGENT_STEPS_TOPIC: AGENT_STEPS_DLQ_TOPIC,
    SYSTEM_METRICS_TOPIC: SYSTEM_METRICS_DLQ_TOPIC,
    SYSTEM_HEALTH_TOPIC: SYSTEM_HEALTH_DLQ_TOPIC,
    MODEL_INFERENCE_TOPIC: MODEL_INFERENCE_DLQ_TOPIC,
    COST_EVENTS_TOPIC: COST_EVENTS_DLQ_TOPIC,
    ANOMALY_EVENTS_TOPIC: ANOMALY_EVENTS_DLQ_TOPIC,
    DRIFT_EVENTS_TOPIC: DRIFT_EVENTS_DLQ_TOPIC,
    ALERTS_EVENTS_TOPIC: ALERTS_EVENTS_DLQ_TOPIC,
    AUDIT_EVENTS_TOPIC: AUDIT_EVENTS_DLQ_TOPIC,
    REGISTRY_EVENTS_TOPIC: REGISTRY_EVENTS_DLQ_TOPIC,
}

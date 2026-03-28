# Руководство по Helm и Kubernetes

## Состав чарта

- API `Deployment` и `Service`
- `Deployment` для воркеров
- `ConfigMap` и ссылки на существующие `Secret`
- `Ingress` с аннотациями для TLS
- `HPA` для масштабирования API
- `KEDA ScaledObject` для масштабирования по отставанию в Kafka
- `PodDisruptionBudget`
- `NetworkPolicy`
- `ServiceMonitor`
- миграционная задача через `Job` hook

## Секреты

Чарт ожидает существующий secret с именем, заданным в `existingSecretName`. Для сценария с External Secrets Operator используйте `deploy/kubernetes/external-secret.example.yaml`.

## KEDA

Для каждого воркера задаются:

- `consumerGroup`
- `primaryTopic`
- минимальное и максимальное количество реплик

Это сохраняет чарт гибким даже при расширении зон ответственности воркеров.

# Руководство по деплою

## Локальный запуск

```bash
cp .env.example .env
uv sync --extra dev
uv run python scripts/dev_stack.py start
```

Варианты локального запуска:

- `uv run python scripts/dev_stack.py start --no-build` поднимает стек без пересборки образов
- `uv run python scripts/dev_stack.py start --skip-smoke` пропускает smoke-проверку
- `uv run python scripts/dev_stack.py smoke` прогоняет только smoke-проверку
- `uv run python scripts/dev_stack.py stop` останавливает стек
- `uv run python scripts/dev_stack.py stop --volumes` останавливает стек и удаляет volumes

После старта локально поднимаются отдельные API-сервисы:

- `http://localhost:8080` — compatibility gateway
- `http://localhost:8081` — registry API
- `http://localhost:8082` — orchestration API
- `http://localhost:8083` — monitoring API
- `http://localhost:8084` — alerting API
- `http://localhost:8085` — audit API

## Kubernetes

```bash
helm upgrade --install workflow-platform helm/workflow-platform \
  -f helm/workflow-platform/values-prod.yaml \
  --namespace workflow-platform --create-namespace
```

Текущий chart разворачивает:

- отдельный `Deployment` для каждого API bounded context;
- отдельный `Service` для каждого API bounded context;
- отдельный `HPA` и `ServiceMonitor` для каждого API bounded context;
- отдельные worker deployment-ы для `projection`, `analytics`, `alerts`;
- `KEDA ScaledObject` для worker deployment-ов;
- migration job, network policy и ingress.

Ingress по умолчанию публикует только `gateway`-сервис. Остальные API-сервисы остаются внутренними `ClusterIP` service-ами и обычно используются:

- внутренними consumer-ами и tooling;
- service mesh/ingress routing;
- внутренней отладкой и административным доступом.

## Миграции

- При локальном запуске через Docker выполняется `uv run alembic upgrade head`
- В Helm используется `Job` hook на `pre-install/pre-upgrade`

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
- `http://localhost:8086` — orchestration query API
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
- отдельные worker deployment-ы для `projection`, `analytics`, `alerts`, `execution`;
- `KEDA ScaledObject` для worker deployment-ов;
- migration job, network policy и ingress.

### Что это значит на уровне процессов

Развертывание теперь разрезано не только по Kubernetes-объектам, но и по runtime-сборке приложения:

- `registry-api` поднимает только registry runtime;
- `orchestration-api` поднимает только orchestration runtime;
- `orchestration-query-api` поднимает только orchestration query runtime;
- `monitoring-api` поднимает только monitoring runtime;
- `alerting-api` поднимает только alerting runtime;
- `audit-api` поднимает только audit runtime;
- `gateway-api` остается совместимым агрегирующим слоем;
- worker deployment-ы поднимают только worker runtime без HTTP bounded context-ов;
- `execution-worker` выполняет LangGraph после получения события `execution.started`, не нагружая API-процесс долгими workflow-задачами.

Дополнительно `orchestration-api` теперь можно рассматривать как чистый command ingress. Он нужен для приема `POST /api/v1/executions`, а query-ручки просмотра выполнений публикуются отдельным `orchestration-query-api`. Это позволяет держать read traffic и heavy execution runtime в разных процессах и масштабировать их независимо.

Это важно для эксплуатации, потому что:

- у сервисов меньше лишних зависимостей на старте;
- авария в одном bounded context меньше влияет на остальные;
- ресурсы CPU и memory проще подбирать под фактическую роль процесса, а не под условный “общий API”.

Ingress по умолчанию публикует только `gateway`-сервис. Остальные API-сервисы остаются внутренними `ClusterIP` service-ами и обычно используются:

- внутренними consumer-ами и tooling;
- service mesh/ingress routing;
- внутренней отладкой и административным доступом.

Если нужен отдельный ingress для `orchestration-query-api`, используйте service-specific режим:

```yaml
apiServices:
  - name: orchestration-query
    enabled: true
    component: orchestration-query
    serviceName: orchestration-query-api
    expose: true
    ingress:
      enabled: true
      separateIngress: true
      path: /orchestration-query
      pathType: Prefix
```

В этом режиме chart создаст отдельный `Ingress` для query-side сервиса, а gateway останется независимой внешней точкой входа.

## Миграции

- При локальном запуске через Docker выполняется `uv run alembic upgrade head`
- В Helm используется `Job` hook на `pre-install/pre-upgrade`

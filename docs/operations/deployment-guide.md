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

### Per-worker tuning

Worker-ы теперь тоже настраиваются не только по `replicaCount` и `resources`, но и по operational-профилю deployment-а. На уровне каждого элемента `workers[]` можно переопределить:

- `terminationGracePeriodSeconds`
- `revisionHistoryLimit`
- `strategy`
- `nodeSelector`
- `tolerations`
- `affinity`
- `topologySpreadConstraints`
- `probes`

Это полезно, когда:

- `execution-worker` нужно держать на нодах с большим запасом CPU;
- `projection-worker` должен обновляться максимально консервативно;
- `alerts-worker` можно запускать на отдельном пуле нод или с другими tolerations;
- `analytics-worker` нужно распределять по зонам независимо от остальных consumer-ролей.

Пример:

```yaml
workers:
  - name: execution
    enabled: true
    role: execution
    replicaCount: 2
    terminationGracePeriodSeconds: 90
    revisionHistoryLimit: 10
    strategy:
      type: RollingUpdate
      rollingUpdate:
        maxUnavailable: 0
        maxSurge: 1
    nodeSelector:
      workload-tier: cpu-heavy
    tolerations:
      - key: "dedicated"
        operator: "Equal"
        value: "cpu-heavy"
        effect: "NoSchedule"
    topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            component: execution
```

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

Если query-side нужно публиковать на отдельном внутреннем hostname, можно переопределить ingress-параметры прямо у сервиса:

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
      className: nginx-internal
      annotations:
        cert-manager.io/cluster-issuer: letsencrypt-internal
      hosts:
        - host: orchestration-query.internal.example.com
      tls:
        - secretName: orchestration-query-tls
          hosts:
            - orchestration-query.internal.example.com
      path: /
      pathType: Prefix
```

Если эти поля не заданы, отдельный ingress унаследует глобальные настройки `ingress.*` chart-а.

### Per-service tuning для API-сервисов

Теперь chart позволяет переопределять operational-профиль прямо у конкретного API-сервиса. Это полезно, когда:

- `gateway` должен держать больше реплик, чем внутренние API;
- `orchestration-api` можно держать компактнее, потому что тяжелое выполнение уже вынесено в `execution-worker`;
- `orchestration-query-api` нужно масштабировать отдельно под read-traffic.
- `registry-api` или `audit-api` нужно закрепить на специальных нодах или с особыми tolerations;
- конкретному сервису нужен другой `terminationGracePeriodSeconds` или собственные pod annotations.
- конкретному сервису нужен свой `strategy`, `revisionHistoryLimit` или распределение по зонам через `topologySpreadConstraints`.

Пример:

```yaml
apiServices:
  - name: gateway
    enabled: true
    replicaCount: 3
    resources:
      requests:
        cpu: 500m
        memory: 1Gi
      limits:
        cpu: "2"
        memory: 2Gi
    autoscaling:
      enabled: true
      minReplicas: 3
      maxReplicas: 10
      targetCPUUtilizationPercentage: 65

  - name: orchestration-query
    enabled: true
    replicaCount: 2
    resources:
      requests:
        cpu: 300m
        memory: 512Mi
      limits:
        cpu: "1"
        memory: 1Gi
    probes:
      readiness:
        path: /api/v1/health/ready
        initialDelaySeconds: 10
        periodSeconds: 10
        failureThreshold: 3
```

Если эти поля не заданы, сервис наследует глобальные значения из `api.*` и `autoscaling.*`. Для этого оставляйте `resources: {}`, `probes: {}` и `autoscaling: {}`.

Точно так же можно переопределять placement и rollout-параметры:

```yaml
apiServices:
  - name: registry
    enabled: true
    terminationGracePeriodSeconds: 60
    podAnnotations:
      cluster-autoscaler.kubernetes.io/safe-to-evict: "true"
    nodeSelector:
      workload-tier: internal-api
    tolerations:
      - key: "dedicated"
        operator: "Equal"
        value: "internal-api"
        effect: "NoSchedule"
    affinity:
      podAntiAffinity:
        preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              topologyKey: topology.kubernetes.io/zone
              labelSelector:
                matchLabels:
                  component: registry
```

Для сервисов с более чувствительным rollout можно переопределить историю ревизий, стратегию обновления и spread constraints:

```yaml
apiServices:
  - name: orchestration-query
    enabled: true
    revisionHistoryLimit: 10
    strategy:
      type: RollingUpdate
      rollingUpdate:
        maxUnavailable: 0
        maxSurge: 2
    topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            component: orchestration-query
```

Если нужно оставить глобальный HPA включенным, но отключить его у конкретного сервиса, используйте:

```yaml
apiServices:
  - name: audit
    enabled: true
    autoscaling:
      enabled: false
```

## Миграции

- При локальном запуске через Docker выполняется `uv run alembic upgrade head`
- В Helm используется `Job` hook на `pre-install/pre-upgrade`

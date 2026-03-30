# Руководство по мониторингу

## Источники сигналов

- HTTP-метрики и метрики выполнения через Prometheus `/metrics`
- Трассы через OpenTelemetry OTLP exporter
- JSON-журналы с `correlation_id`, `trace_id` и `principal_id`

## Как сервис выбирается в рантайме

Перед тем как разбирать метрики и трассы, важно понимать, какой именно сервисный процесс вообще поднят в контейнере.

Локально и в Kubernetes API-контейнер использует один и тот же bootstrap-скрипт:

- [docker/start-api.sh](d:/p/FastAPI/FastAPI_Layers/docker/start-api.sh)

Схема работы простая:

1. контейнер читает переменную окружения `APP_COMPONENT`;
2. `start-api.sh` по `case` выбирает нужный ASGI entrypoint;
3. `uvicorn` запускает конкретный модуль:
   - `gateway` -> `app.main:app`
   - `registry` -> `app.services.registry_api:app`
   - `orchestration` -> `app.services.orchestration_api:app`
   - `orchestration-query` -> `app.services.orchestration_query_api:app`
   - `monitoring` -> `app.services.monitoring_api:app`
   - `alerting` -> `app.services.alerting_api:app`
   - `audit` -> `app.services.audit_api:app`

Это важно для мониторинга, потому что:

- у каждого процесса свой `service_name`;
- у каждого процесса свой `/metrics`;
- у каждого процесса свои трассы OpenTelemetry;
- Prometheus и логирование видят не “общий API”, а конкретный bounded context.

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

## Redis

### Зачем Redis нужен в проекте

Redis в этом проекте используется как легковесная инфраструктурная зависимость для operational-контура. Сейчас он не является основным persisted store платформы и не хранит бизнес-данные уровня registry, execution history или audit trail. Эти данные хранятся в PostgreSQL. Роль Redis здесь более прикладная и инфраструктурная: он нужен как быстрый внешний runtime-компонент, доступность которого проверяется системой и который может использоваться для координации и короткоживущих сигналов.

### Где Redis подключен

- в конфигурации приложения через `REDIS_URL`;
- в локальном docker-compose как отдельный сервис `redis`;
- в Helm values через параметр `config.redisUrl`;
- в health-контуре через проверку `PING`.

Ключевой код:

- `app/modules/monitoring/health.py`
- `docker-compose.yml`
- `helm/workflow-platform/values.yaml`

### Как Redis используется сейчас

В текущей реализации Redis используется в первую очередь в двух сценариях:

- как обязательная внешняя зависимость, readiness которой проверяется через `/api/v1/health/ready` и `/api/v1/health/deep`;
- как часть инфраструктурного контура, который можно использовать для координационных механизмов без изменения общей архитектуры платформы.

Практически это означает:

- если Redis недоступен, health-контур помечает компонент как `failing`;
- это дает ранний operational сигнал, что часть инфраструктурного контура деградировала;
- Redis уже встроен в конфигурацию и deployment-модель, поэтому его можно безопасно использовать для будущих runtime-сценариев.

### В каких сценариях Redis особенно полезен

Даже если в текущем коде Redis используется минимально, для этой платформы он полезен в следующих реальных сценариях:

- распределенные блокировки для запуска редких операций;
- dedupe или rate-limit state;
- coordination state между несколькими worker-ами;
- кэш краткоживущих operational данных;
- хранение short-lived флагов и сигналов деградации;
- лидер-элекция для отдельных фоновых задач.

Иными словами, Redis здесь подготовлен как operational building block. Он уже входит в runtime и health-модель платформы, поэтому его можно расширять без смены архитектурного каркаса.

## Prometheus

### Что Prometheus делает в проекте

Prometheus отвечает за сбор технических runtime-метрик процесса и worker-контуров. Это внешний контур scrape-based мониторинга, который читает `/metrics` и сохраняет time-series данные для dashboards, alert rules и анализа нагрузки.

Важно различать два слоя:

- `/metrics` — Prometheus exposition endpoint с runtime-метриками процесса;
- `/api/v1/metrics` — read-side API для сохраненных metric events в PostgreSQL.

Это не одно и то же:

- первый слой нужен Prometheus и инфраструктурному мониторингу;
- второй слой нужен приложению, аналитике и внутреннему API-чтению.

### Где Prometheus развернут

Локально:

- в `docker-compose.yml` есть отдельный сервис `prometheus`;
- конфигурация scrape находится в `docker/prometheus.yml`;
- Prometheus доступен на `http://localhost:9090`.

В Kubernetes:

- API deployment аннотирован для scrape;
- chart содержит `ServiceMonitor` в `helm/workflow-platform/templates/servicemonitor.yaml`;
- Prometheus Operator может автоматически подхватить сервис через этот `ServiceMonitor`.

### Что именно собирает Prometheus

Ключевые runtime-метрики определены в `app/core/metrics.py`:
Ключевые runtime-метрики определены в `app/core/metrics.py`:

- `workflow_platform_http_requests_total` — общее число HTTP-запросов;
- `workflow_platform_http_request_duration_seconds` — latency HTTP-запросов;
- `workflow_platform_execution_step_duration_seconds` — длительность шагов выполнения;
- `workflow_platform_kafka_consumer_lag` — lag consumer group по Kafka topics;
- `workflow_platform_active_executions` — число активных выполнений;
- `workflow_platform_compute_cost_usd_total` — накопленная стоимость вычислений.

### Где эти метрики обновляются

- HTTP-метрики обновляются middleware-слоем;
- `workflow_platform_execution_step_duration_seconds` обновляется в orchestration-сервисе при завершении шага;
- `workflow_platform_kafka_consumer_lag` обновляется в Kafka consumer loop;
- `workflow_platform_active_executions` увеличивается и уменьшается вокруг lifecycle выполнения;
- `workflow_platform_compute_cost_usd_total` увеличивается на основе telemetry каждого model call.

Ключевые файлы:

- `app/core/metrics.py`
- `app/messaging/kafka.py`
- `app/modules/orchestration/service.py`
- `app/main.py`

### Где и как Prometheus получает данные

Локально:

- Prometheus скрапит отдельные API-сервисы по конфигу из [docker/prometheus.yml](d:/p/FastAPI/FastAPI_Layers/docker/prometheus.yml):
  - `api-gateway:8080`
  - `registry-api:8080`
  - `orchestration-api:8080`
  - `orchestration-query-api:8080`
  - `monitoring-api:8080`
  - `alerting-api:8080`
  - `audit-api:8080`

У каждого сервиса свой `job_name`, например:

- `workflow-gateway`
- `workflow-registry`
- `workflow-orchestration`
- `workflow-orchestration-query`
- `workflow-monitoring`
- `workflow-alerting`
- `workflow-audit`

Это дает отдельные time series по сервисам и позволяет видеть, какой bounded context нагружен или деградирует.

Если `orchestration-query-api` публикуется отдельным ingress, scrape-конфигурация не меняется: Prometheus по-прежнему читает `/metrics` через внутренний `Service`, а не через внешний ingress. Это важно, потому что observability остается независимой от того, публикуется ли сервис наружу.

В Kubernetes:

- Prometheus Operator использует `ServiceMonitor`;
- либо может использоваться прямой scrape через annotations на pod/service;
- endpoint остается тем же: `/metrics`.

На стороне Helm это отражается так:

- для каждого API service создается отдельный `Service`;
- для каждого API service создается отдельный `ServiceMonitor`;
- labels содержат `component`, поэтому Prometheus может различать сервисы даже при одинаковом приложении и одном chart.

## OpenTelemetry

### Что OpenTelemetry делает в проекте

OpenTelemetry используется для трассировки запроса и внутренних операций. Если Prometheus отвечает на вопрос “что и насколько часто происходит”, то OpenTelemetry отвечает на вопрос “как именно прошел конкретный запрос или конкретное выполнение и где оно замедлилось”.

В проекте OpenTelemetry нужен для:

- трассировки HTTP-запросов FastAPI;
- трассировки работы с SQLAlchemy;
- ручных span-ов вокруг Kafka publish и consume;
- переноса `trace_id` через event envelope и журналы.

### Где OpenTelemetry подключен

Основная настройка находится в `app/core/observability.py`.
Основная настройка находится в `app/core/observability.py`.

Что там происходит:

- создается `TracerProvider`;
- задается ресурс с `service.name` и `deployment.environment`;
- если задан `OTEL_EXPORTER_OTLP_ENDPOINT`, включается OTLP exporter;
- FastAPI инструментируется через `FastAPIInstrumentor`;
- SQLAlchemy инструментируется через `SQLAlchemyInstrumentor`.

### Как OpenTelemetry развернут локально

В `docker-compose.yml` есть отдельный сервис `otel-collector`.

Его конфигурация находится в [docker/otel-collector-config.yaml](d:/p/FastAPI/FastAPI_Layers/docker/otel-collector-config.yaml).

Сейчас локальный collector:

- принимает OTLP по gRPC и HTTP;
- выводит traces в `debug` exporter.

Это означает, что локальный collector не хранит трассы как production backend, а просто подтверждает сам факт их поступления и печатает их в логи контейнера. Для локальной разработки этого достаточно, чтобы:

- проверить, что сервис вообще отправляет trace-данные;
- убедиться, что `service.name` и `trace_id` приходят корректно;
- не тащить в локальный стек Tempo, Jaeger или другой отдельный tracing backend.

Это удобно для локальной разработки:

- можно убедиться, что трассы вообще создаются;
- не нужен внешний production tracing backend;
- при необходимости later-stage deployment можно переключить exporter на Jaeger, Tempo, OTLP gateway или другой backend.

### Где OpenTelemetry используется в коде

- HTTP-слой — автоматическая инструментализация FastAPI;
- SQLAlchemy — автоматическая инструментализация ORM/DB;
- Kafka — ручные span-ы вида `kafka.publish.<topic>` и `kafka.consume.<topic>`;
- бизнес-поток выполнения — `trace_id` переносится в event envelope и далее в audit, projections и execution history.

Это позволяет связывать между собой:

- входящий HTTP-запрос;
- публикацию события;
- обработку Kafka consumer-ом;
- запись в базу;
- публикацию follow-up событий.

### Как OpenTelemetry связан с микросервисной схемой

После перехода на микросервисы у каждого API-сервиса свой runtime и свой `service_name`. Это важно для OTel, потому что именно `service.name` становится основным признаком принадлежности trace к сервису.

Практически это выглядит так:

- `docker-compose.yml` задает `SERVICE_NAME` для каждого контейнера;
- сервисный entrypoint создает свой runtime с этим именем;
- `app/core/observability.py` использует `service.name` при регистрации tracer provider resource;
- в collector и downstream backend трассы уже различаются как `gateway-api`, `registry-api`, `orchestration-api`, `orchestration-query-api` и т.д.

За счет этого можно:

- отличать деградацию `registry-api` от деградации `orchestration-api` и `orchestration-query-api`;
- видеть, где именно оборвался запрос: на gateway, на orchestration или на worker-side event handling;
- сопоставлять трассы с логами и audit trail по `trace_id`.

### Практическая польза OpenTelemetry здесь

OpenTelemetry особенно полезен, когда нужно:

- понять, где именно замедлилось выполнение;
- отличить проблему API от проблемы БД, Kafka или внешнего model endpoint;
- расследовать цепочку событий одного execution run;
- связать техническую трассу с audit trail и structured logs.

## KEDA

### Что такое KEDA

KEDA — это Kubernetes Event-Driven Autoscaling. Проще говоря, это механизм, который умеет автоматически масштабировать workload не только по CPU и памяти, как классический HPA, но и по внешним event-driven сигналам, например:

- lag в Kafka;
- длина очереди;
- сообщения в брокере;
- метрики облачных сервисов;
- cron-based события.

Для этой платформы это особенно важно, потому что worker-ы обрабатывают Kafka topics, а значит их нагрузка лучше измеряется не CPU, а тем, насколько быстро они успевают разгребать очередь сообщений.

### Как KEDA используется в проекте

В Helm chart есть шаблон `helm/workflow-platform/templates/keda-scaledobject.yaml`.
В Helm chart есть шаблон `helm/workflow-platform/templates/keda-scaledobject.yaml`.

Он создает `ScaledObject` для каждого включенного worker-а.

Что задается в `ScaledObject`:

- `scaleTargetRef` — какой Deployment масштабировать;
- `pollingInterval` — как часто проверять источник сигнала;
- `cooldownPeriod` — как быстро уменьшать число реплик;
- `minReplicaCount` и `maxReplicaCount`;
- Kafka trigger с `bootstrapServers`, `consumerGroup`, `topic` и `lagThreshold`.

### Почему KEDA полезна именно здесь

Если projection, analytics или alert workers не успевают обрабатывать Kafka, наиболее корректный operational сигнал — это отставание consumer group, а не загрузка CPU как таковая. KEDA использует именно этот сигнал.

Преимущества:

- масштабирование ближе к реальной очереди работы;
- более быстрое восстановление после всплеска событий;
- меньший риск долгого хвоста lag в projection и alert pipeline;
- естественное соответствие event-driven архитектуре.

### Где KEDA развертывается

Локально в `docker-compose` KEDA не поднимается.

В production-контуре KEDA предполагается как часть Kubernetes-кластера:

- chart генерирует `ScaledObject`;
- сам оператор KEDA должен быть установлен в кластере отдельно;
- после этого worker deployment-ы масштабируются по lag в Kafka.

Если KEDA недоступна, проект может использовать более простой fallback через HPA для API и статическое число worker replicas.

## Есть ли уже “AI агенты” для мониторинга

В текущем проекте уже есть специализированные monitoring workers, но это не LLM-агенты и не автономные reasoning-агенты в широком смысле.

Что уже есть:

- `metrics-aggregation-worker` — публикует агрегирующие metric events;
- `anomaly-worker` — анализирует метрики и стоимость через threshold, rolling std и z-score;
- `drift-worker` — анализирует модельные сигналы и ищет drift;
- `alert-worker` — превращает anomaly/drift events в alerts.

Ключевой файл:

- `app/workers.py`

Что важно понимать:

- это специализированные event-driven аналитические worker-ы;
- они работают по детерминированным правилам и статистическим эвристикам;
- они не используют LLM для анализа инцидентов;
- они не принимают самостоятельных операторских решений.

То есть monitoring automation уже есть, но это пока rule-based и metric-based контур, а не полноценные “AI-агенты мониторинга”.

### Можно ли добавить настоящих monitoring-агентов

Да, архитектурно платформа к этому готова.

Наиболее естественные точки расширения:

- агент-аналитик, который объясняет причину anomaly на основе цепочки событий;
- агент-диагност, который собирает trail по `correlation_id`, метрикам и логам;
- агент-рекомендатель, который предлагает remediation steps;
- агент-постмортем-ассистент, который формирует черновик incident summary.

Но в текущем состоянии репозитория таких LLM-based monitoring agents еще нет.

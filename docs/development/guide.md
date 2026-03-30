# Руководство разработчика

## Цель раздела

Этот документ описывает повседневную разработку в репозитории: как поднять локальную среду, как устроены модули, где вносить изменения, как тестировать результат и какие правила помогают сохранять согласованность архитектуры.

## Базовые требования

- Python `3.13+`
- `uv`
- Docker и Docker Compose
- Git
- GNU Make или совместимый `make`
- Доступ к локальным портам `5432`, `6379`, `8080-8085`, `9090`, `9092`

## Быстрый старт для разработчика

1. Создайте локальный файл окружения:

```bash
cp .env.example .env
```

2. Установите зависимости:

```bash
uv sync --extra dev
```

3. Поднимите инфраструктуру и сервисы рекомендуемой командой:

```bash
uv run python scripts/dev_stack.py start
```

Эта команда не только поднимает контейнеры, но и автоматически наполняет локальный реестр demo-данными. После старта в Swagger и в read API уже будут доступны demo graph, agents, models, environments и deployments.

4. При необходимости используйте платформенные обертки:

```bash
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

```bash
sh scripts/start-local.sh
```

5. Если миграции не применились автоматически, выполните:

```bash
make migrations-upgrade
```

6. Проверьте, что приложение отвечает:

- Gateway API: `http://localhost:8080`
- Registry API: `http://localhost:8081`
- Orchestration API: `http://localhost:8082`
- Orchestration Query API: `http://localhost:8086`
- Monitoring API: `http://localhost:8083`
- Alerting API: `http://localhost:8084`
- Audit API: `http://localhost:8085`
- Swagger gateway: `http://localhost:8080/docs`
- Swagger registry: `http://localhost:8081/docs`
- Swagger orchestration: `http://localhost:8082/docs`
- Swagger orchestration query: `http://localhost:8086/docs`
- Метрики gateway: `http://localhost:8080/metrics`
- Prometheus: `http://localhost:9090`

## Режимы запуска

### Полный локальный стек

Используется для сквозной проверки API, фоновых воркеров, Kafka-потоков и проекций.

```bash
uv run python scripts/dev_stack.py start
```

Ключевые режимы:

- `uv run python scripts/dev_stack.py start --no-build` поднимает стек без пересборки образов
- `uv run python scripts/dev_stack.py start --skip-seed` поднимает стек, но не создает demo-данные
- `uv run python scripts/dev_stack.py start --skip-smoke` поднимает стек и пропускает smoke-проверку
- `uv run python scripts/dev_stack.py seed` отдельно создает или восстанавливает demo-данные
- `uv run python scripts/seed_demo_data.py` напрямую запускает идемпотентный seed-скрипт
- `uv run python scripts/dev_stack.py smoke` прогоняет только smoke-проверку уже поднятого окружения
- `uv run python scripts/dev_stack.py stop` останавливает локальный стек
- `uv run python scripts/dev_stack.py stop --volumes` останавливает стек и удаляет volumes

### Микросервисный режим разработки

После перехода на микросервисную архитектуру bounded context-ы API поднимаются как отдельные процессы и контейнеры. Это означает:

- `registry-api` отвечает только за реестровый контур;
- `orchestration-api` отвечает только за command ingress execution-контура;
- `orchestration-query-api` отвечает только за read-side execution history;
- `monitoring-api` отвечает только за monitoring read-side и health;
- `alerting-api` отвечает только за alert read-side;
- `audit-api` отвечает только за audit read-side;
- `gateway-api` остается агрегирующим compatibility layer.

Для Kubernetes/Helm это важно не только логически, но и operationally: каждый API-сервис теперь можно отдельно тюнить по `replicaCount`, `resources`, `probes`, `autoscaling`, `terminationGracePeriodSeconds`, `revisionHistoryLimit`, `strategy`, `podAnnotations`, `nodeSelector`, `tolerations`, `affinity` и `topologySpreadConstraints`, а не только разносить по разным контейнерам. Для наследования глобального HPA оставляйте `autoscaling: {}`, а для локального отключения HPA у сервиса задавайте `autoscaling.enabled: false`.

Для разработчика это полезно в двух сценариях:

- можно локально проверять только один bounded context через отдельный Swagger;
- можно независимо смотреть логи и health конкретного сервиса, а не всего бывшего монолита.

### Какой runtime у какого сервиса

Важно различать два уровня:

- отдельный HTTP entrypoint;
- отдельный process runtime с собственным набором зависимостей.

В проекте уже реализованы оба уровня. Это значит, что сервисы не просто слушают разные порты, а действительно поднимают разный dependency graph.

| Сервис | Runtime-модули | Практический смысл |
| --- | --- | --- |
| `gateway-api` | `registry`, `orchestration`, `monitoring`, `alerting`, `audit` | совместимый агрегирующий вход для legacy-сценариев и общего Swagger |
| `registry-api` | `registry` | удобно разрабатывать и тестировать реестр без orchestration и analytics слоя |
| `orchestration-api` | `orchestration` | удобно разрабатывать command ingress execution flow без read-side и тяжелого runtime |
| `orchestration-query-api` | `orchestration-query` | удобно разрабатывать materialized историю выполнений и `GET /executions*` отдельно от command ingress |
| `monitoring-api` | `monitoring` | изолированная работа с health и read-side метриками |
| `alerting-api` | `alerting` | изолированный просмотр alert read model |
| `audit-api` | `audit` | изолированный доступ к audit trail |
| `worker` | `workers` | только event consumers, projector, detector-ы и alert processing |

С практической точки зрения это дает три преимущества:

- быстрее стартуют отдельные процессы;
- проще локализовать регресс, потому что упавший runtime затрагивает меньшую часть системы;
- легче выносить bounded context в полностью отдельные сервисы без переписывания внутреннего wiring.

### Как работает `APP_COMPONENT`

Для контейнерного запуска ключевая переменная — `APP_COMPONENT`.

Где она используется:

- задается в `docker-compose.yml` для каждого API-контейнера;
- передается в Kubernetes deployment через Helm;
- читается скриптом [docker/start-api.sh](d:/p/FastAPI/FastAPI_Layers/docker/start-api.sh).

Что она определяет:

- какой ASGI entrypoint будет запущен;
- какой bounded context API реально поднимется;
- какой `service_name` увидят логи, Prometheus и OpenTelemetry.

Матрица соответствия:

| `APP_COMPONENT` | Запускаемый модуль |
| --- | --- |
| `gateway` | `app.main:app` |
| `registry` | `app.services.registry_api:app` |
| `orchestration` | `app.services.orchestration_api:app` |
| `orchestration-query` | `app.services.orchestration_query_api:app` |
| `monitoring` | `app.services.monitoring_api:app` |
| `alerting` | `app.services.alerting_api:app` |
| `audit` | `app.services.audit_api:app` |

Если сервис стартует “не туда”, почти всегда проблема находится в одном из трех мест:

- неверно задан `APP_COMPONENT`;
- неверно задан `SERVICE_NAME`;
- контейнер стартовал не через `docker/start-api.sh`, а через другой entrypoint.

### Какие demo-данные создает локальный seed

Локальный seed нужен для двух задач:

- чтобы Swagger и read API были полезны сразу после первого запуска;
- чтобы у команды был стабильный набор сущностей для smoke, демонстраций и ручной проверки сценариев.

Скрипт создает и поддерживает в актуальном состоянии следующие сущности:

- `billing-operations-graph`
- `validator-enabled-graph`
- `internal-llm-gateway`
- `internal-analyst-gateway`
- `dev`
- `prod`
- `billing-ops-agent`
- `support-triage-agent`
- `deployment-review-agent`
- три demo deployment-конфигурации, привязанные к этим агентам, моделям и окружениям

Скрипт [scripts/seed_demo_data.py](d:/p/FastAPI/FastAPI_Layers/scripts/seed_demo_data.py) идемпотентен. Если demo-сущность уже существует, повторный запуск использует ее повторно и не создает дубль.

### Локальная разработка приложения поверх контейнерной инфраструктуры

Полезно, когда нужно быстро менять Python-код, но не хочется каждый раз пересобирать контейнер API.

1. Поднимите только инфраструктуру:

```bash
docker compose up postgres redis kafka otel-collector prometheus
```

2. Запустите приложение локально:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Если нужно поднять конкретный сервис, используйте его entrypoint напрямую:

```bash
uv run uvicorn app.services.registry_api:app --reload --host 0.0.0.0 --port 8081
```

```bash
uv run uvicorn app.services.orchestration_api:app --reload --host 0.0.0.0 --port 8082
```

```bash
uv run uvicorn app.services.orchestration_query_api:app --reload --host 0.0.0.0 --port 8086
```

```bash
uv run uvicorn app.services.monitoring_api:app --reload --host 0.0.0.0 --port 8083
```

```bash
uv run uvicorn app.services.alerting_api:app --reload --host 0.0.0.0 --port 8084
```

```bash
uv run uvicorn app.services.audit_api:app --reload --host 0.0.0.0 --port 8085
```

3. При необходимости отдельно запустите воркеры:

```bash
set WORKER_ROLE=projection
uv run python -m app.worker
```

```bash
set WORKER_ROLE=analytics
uv run python -m app.worker
```

```bash
set WORKER_ROLE=alerts
uv run python -m app.worker
```

## Работа через uv

`uv` является основным инструментом для локальной разработки в этом репозитории.

- `uv sync --extra dev` создает и синхронизирует виртуальное окружение проекта
- `uv run ...` запускает команды внутри проектного окружения
- `uv lock` обновляет lock-файл зависимостей
- `uv run python scripts/dev_stack.py ...` является рекомендуемой точкой входа для локального Docker lifecycle

Рекомендуемый базовый цикл:

```bash
uv sync --extra dev
uv run python scripts/dev_stack.py start --no-build --skip-smoke
uv run pytest
uv run mypy app tests
uv run mkdocs build
```

## Как смотреть таблицы в Markdown

В проекте много таблиц в `.md`-файлах: архитектурные матрицы, Kafka-контракты, roadmap-таблицы и operational checklist. Лучше всего читать их не в сыром виде, а через рендер Markdown.

Основные способы:

- `uv run mkdocs serve` поднимает локальный сайт документации, где таблицы уже отрисованы как обычные HTML-таблицы.
- `uv run mkdocs build` собирает статическую версию документации в каталог `site/`, после чего ее можно открыть браузером.
- встроенный preview в IDE обычно тоже корректно рендерит pipe-таблицы Markdown.

Практические команды:

```bash
uv run mkdocs serve
```

```bash
uv run mkdocs build
```

На что обратить внимание:

- если таблица в сыром `.md` выглядит “криво”, это не значит, что она неверная: главное, чтобы у нее были корректные разделители `|` и строка с `---`;
- большие таблицы удобнее читать именно через MkDocs, потому что браузер лучше переносит строки и сохраняет выравнивание;
- если вы редактируете таблицу, после правок лучше сразу прогнать `uv run mkdocs build`, чтобы убедиться, что документ отображается как ожидается.

## Структура репозитория

### Код приложения

- `app/main.py` создает FastAPI-приложение и подключает middleware, роуты и telemetry.
- `app/runtime.py` собирает runtime-контейнер приложения: publisher, projection service, детекторы, сервисы и фабрики сессий.
- `app/core/` содержит конфигурацию, безопасность, наблюдаемость, middleware и общие ошибки.
- `app/db/` содержит SQLAlchemy-модели, базу, репозитории и создание сессий.
- `app/domain/` содержит общие схемы DTO, event envelope и перечисления.
- `app/messaging/` содержит Kafka producer/consumer слой и карту топиков.

### Модульные области

- `app/modules/registry/` отвечает за командный контур реестровых сущностей.
- `app/modules/orchestration/` отвечает за запуск сценариев и step-level события.
- `app/modules/monitoring/` отвечает за health, performance query side, anomaly и drift logic.
- `app/modules/alerting/` отвечает за дедупликацию, cooldown и выдачу алертов.
- `app/modules/audit/` отвечает за публикацию и чтение аудита.
- `app/projections/` материализует события в PostgreSQL read models.
- `app/workers.py` задает состав фоновых workers и их роли.

### Инфраструктурные каталоги

- `alembic/` миграции базы данных.
- `docker/` Dockerfile и runtime-скрипты контейнеров.
- `helm/` production-ready chart.
- `deploy/` примеры манифестов и интеграций.
- `docs/` документация проекта.
- `scripts/` служебные скрипты, например bootstrap топиков.
- `tests/` модульные и интеграционные тесты.

Подробный разбор того, что делает каждый модуль и зачем он нужен, вынесен в отдельный справочник:

- [Справочник по модулям](modules.md)

## Использование LangGraph в проекте

`LangGraph` остается основой orchestration-слоя и используется в [app/modules/orchestration/graph.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/graph.py) для сборки сценария выполнения.

В текущей реализации:

- `StateGraph` описывает граф состояния выполнения;
- `START` и `END` задают явные точки входа и завершения;
- узлы `planner`, `tool_runner` и `reviewer` оформлены как асинхронные шаги;
- вызов `ainvoke(...)` запускает исполнение графа;
- step-level события и telemetry публикуются через `step_emitter`.

Подробное практическое руководство вынесено в [docs/development/langgraph.md](d:/p/FastAPI/FastAPI_Layers/docs/development/langgraph.md).

### Как включить ветку `validator`

По умолчанию workflow идет по базовому маршруту:

- `planner -> tool_runner -> reviewer`

Чтобы включить дополнительный шаг проверки, передайте во входной payload флаг:

```json
{
  "graph_definition_id": "graph-validator-demo",
  "input_payload": {
    "objective": "Validate rollout plan for a degraded workflow",
    "require_validation": true
  }
}
```

Тогда `LangGraph` выберет маршрут:

- `planner -> tool_runner -> validator -> reviewer`

Что важно проверить после включения или изменения этой ветки:

- `output_payload.validation_summary` появляется в `execution.finished`;
- read API возвращает шаг `validator` в списке `steps`;
- Kafka публикует дополнительный `step.completed` для `validator`;
- интеграционные тесты на API и Kafka остаются зелеными.

## Архитектурные правила разработки

### CQRS

- Контур записи публикует события в Kafka.
- Контур чтения работает только через PostgreSQL projections.
- API не должен читать Kafka напрямую.

### Границы модулей

- Внутри одного модуля можно держать API, commands, queries и schemas.
- Общие cross-cutting сущности должны жить в `app/core/`, `app/domain/` или `app/db/`.
- Если модулю требуется обмен данными с другим модулем, это лучше делать через domain events, а не через плотную связанность Python-объектов.

### Изменения в модели данных

- Изменения ORM-моделей должны сопровождаться обновлением Alembic.
- Любое изменение событийного payload должно быть согласовано с projection layer и тестами.
- При добавлении новых полей в DTO нужно проверить сериализацию, read side и integration tests.

## Обычный цикл разработки

1. Найдите модуль, которому принадлежит изменение.
2. Внесите код в write side, если это команда или публикация события.
3. Обновите projections, если меняется read model.
4. Обновите query layer и API, если меняется контракт чтения.
5. Добавьте или исправьте тесты.
6. Прогоните линтеры, типизацию и тесты.
7. Обновите документацию, если изменение затрагивает поведение системы.

## Как вносить изменения по сценариям

### Добавление нового API endpoint

1. Добавьте схему запроса или ответа в модульный `schemas.py` или `app/domain/schemas.py`.
2. Добавьте use case в `commands.py` или `queries.py`.
3. Подключите endpoint в модульный `api.py`.
4. Если endpoint пишет данные, опубликуйте событие в Kafka.
5. Если endpoint читает данные, убедитесь, что нужная проекция уже материализуется.
6. Добавьте unit или integration test.

### Добавление новой доменной сущности

1. Добавьте SQLAlchemy-модель в `app/db/models.py`.
2. Добавьте DTO в `app/domain/schemas.py`.
3. Добавьте write-side команды и query-side запросы.
4. Добавьте обработку соответствующих событий в `app/projections/projector.py`.
5. Создайте миграцию.
6. Обновите документацию API и архитектуры.

### Добавление нового Kafka consumer

1. Опишите или переиспользуйте topic в `app/messaging/topics.py`.
2. Создайте handler в `app/workers.py` или в модуле, которому принадлежит логика.
3. Подключите worker в `build_workers`.
4. Настройте KEDA или HPA-конфиг, если новый consumer должен масштабироваться отдельно.
5. Добавьте тест на happy path и DLQ path.

### Добавление новой метрики

1. Зарегистрируйте Prometheus metric в `app/core/metrics.py`, если она нужна на runtime-уровне.
2. Если это доменная метрика, публикуйте `metric.recorded` в `system.metrics`.
3. При необходимости обновите summary query в `app/modules/monitoring/queries.py`.
4. Отразите метрику в документации мониторинга.

## Работа с базой данных и миграциями

### Создание миграции

```bash
alembic revision -m "add new entity"
```

### Применение миграций

```bash
uv run alembic upgrade head
```

### Откат миграций

```bash
uv run alembic downgrade -1
```

### Практические правила

- Не меняйте таблицы и колонки без синхронного обновления ORM, DTO и projections.
- Если меняется семантика данных, добавляйте migration-safe defaults.
- Проверяйте локально создание пустой базы и применение миграций с нуля.

## Тестирование

### Основные команды

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run black .
uv run ruff check . --fix
```

```bash
uv run mypy app tests
```

### Что тестировать обязательно

- Новый command handler
- Новый query service
- Новую обработку событий в projection layer
- Изменения в anomaly или drift logic
- Аутентификацию и RBAC, если меняются права доступа
- Kafka flow, если меняются retries, idempotency или DLQ

### Структура тестов

- `tests/unit/` для чистой бизнес-логики без тяжелой инфраструктуры
- `tests/integration/` для API, runtime, projections и фона

## Качество кода

Проект использует:

- `ruff`
- `black`
- `mypy`
- `pytest`
- `pre-commit`

### Локальная подготовка hooks

```bash
uv run pre-commit install
```

### Практика по качеству

- Предпочитайте явные типы в публичных интерфейсах.
- Не добавляйте связанность между модулями без необходимости.
- Не смешивайте write side и read side в одном endpoint.
- Старайтесь держать event payload компактным и стабильным.
- При добавлении новых enum или status обновляйте тесты и документацию.

## Отладка

### Логи

- Логи структурированы и подходят для машинной обработки.
- Для локальной отладки gateway смотрите `docker compose logs -f api-gateway`.
- Для конкретных API-сервисов используйте `docker compose logs -f registry-api`, `orchestration-api`, `orchestration-query-api`, `monitoring-api`, `alerting-api`, `audit-api`.
- Для воркеров используйте `docker compose logs -f worker-projection`, `worker-analytics`, `worker-alerts`.

Если сервис стартует, но работает “не с тем” набором зависимостей, первым делом проверьте:

- переменную `APP_COMPONENT` в контейнере;
- какой entrypoint запускается через `docker/start-api.sh`;
- какой `modules=(...)` передается в `get_runtime(...)` внутри сервисного файла из `app/services/`.

### Проверка Kafka

- Убедитесь, что топики созданы и доступны.
- Проверяйте lag потребителей через метрики и Prometheus.
- При проблемах с обработкой смотрите DLQ topics.

Для локальной отладки Kafka используйте готовый скрипт:

```bash
uv run python scripts/kafka_debug.py all
```

Практические команды:

- `uv run python scripts/kafka_debug.py topics` показывает все topics
- `uv run python scripts/kafka_debug.py groups` показывает все consumer groups
- `uv run python scripts/kafka_debug.py lag` показывает lag по всем groups
- `uv run python scripts/kafka_debug.py dlq` показывает только DLQ-topics
- `uv run python scripts/kafka_debug.py describe-group projection-consumers` помогает искать застрявшую read-side обработку
- `uv run python scripts/kafka_debug.py describe-topic agent.executions` помогает проверить partitions и offsets конкретного topic
- `uv run python scripts/kafka_debug.py peek-topic agent.executions --max-messages 1 --from-beginning` показывает реальный event envelope
- `uv run python scripts/kafka_debug.py peek-dlq agent.steps.dlq --max-messages 1 --from-beginning` помогает быстро посмотреть ошибочное сообщение из DLQ
- `uv run python scripts/kafka_debug.py peek-topic agent.executions --from-beginning --event-type execution.finished` позволяет искать только нужный тип события
- `uv run python scripts/kafka_debug.py peek-topic agent.executions --from-beginning --payload-field execution_run.id=<execution_id>` позволяет найти конкретный запуск по payload

### Проверка проекций

- Если write endpoint вернул `accepted`, но read API не отражает изменения, первым делом проверьте projection worker.
- Затем проверьте таблицу `processed_events`.
- Затем проверьте, не менялся ли event payload без обновления `projector.py`.

### Проверка health endpoints

- `/health/live` отвечает за liveness.
- `/health/ready` отвечает за readiness.
- `/health/deep` проверяет внешние зависимости и фоновые компоненты.

## Наблюдаемость при разработке

При локальной разработке полезно одновременно держать открытыми:

- `/docs`
- `/metrics`
- Prometheus UI
- логи API
- логи соответствующего worker-процесса

Если меняется путь события через Kafka, проверяйте:

1. публикуется ли событие;
2. подхватывает ли его нужный consumer group;
3. обновилась ли проекция;
4. корректно ли отвечает read API.

## Правила обновления документации

Документацию нужно обновлять, если меняется хотя бы один из пунктов:

- API-контракт
- схема событий
- состав Helm values
- deployment-процедура
- runbook инцидента
- модель данных

Минимальный набор для проверки после правок в docs:

```bash
uv run mkdocs build
```

## Checklist перед merge

- Код проходит `uv run ruff check .`
- Код проходит `uv run mypy app tests`
- Нужные тесты добавлены и проходят
- Миграции синхронизированы с ORM
- Документация обновлена
- Не добавлены реальные секреты, пароли и токены
- Внешние конфиги используют безопасные плейсхолдеры

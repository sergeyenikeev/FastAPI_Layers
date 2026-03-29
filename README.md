# Платформа эксплуатации сценариев

Централизованная платформа, готовая к промышленной эксплуатации и быстрому выводу распределенных сценариев в продакшен. Репозиторий реализует модульный монолит с готовыми границами для последующего выделения сервисов, событийную архитектуру на Kafka, CQRS с проекциями в PostgreSQL и эксплуатационный контур для Kubernetes.

## Назначение

- Быстрый запуск распределенных сценариев в продакшене
- Единый реестр агентов, графов, моделей, инструментов, окружений и деплоев
- Централизованный сбор телеметрии выполнения, детектирование аномалий и дрейфа, алертинг и аудит
- Готовые артефакты для Docker, Kubernetes, Helm, KEDA, Prometheus и ingress с поддержкой TLS

## Архитектура

- `FastAPI` предоставляет версионированный API, эндпоинты состояния и `/metrics`
- `Kafka` служит магистралью доменных и системных событий
- `PostgreSQL` хранит модели чтения, проекции и журнал аудита
- `Redis` используется для координации и сигналов heartbeat от рабочих процессов
- Движок оркестрации исполняет сценарии с трассировкой на уровне шагов
- `Prometheus` и `OpenTelemetry` обеспечивают метрики и трассировку

Подробное описание архитектуры находится в [docs/architecture/overview.md](docs/architecture/overview.md).
Подробное руководство по разработке находится в [docs/development/guide.md](docs/development/guide.md).
Руководство по использованию `LangGraph` находится в [docs/development/langgraph.md](docs/development/langgraph.md).

## Поток событий

1. API принимает команду, проверяет аутентификацию и RBAC, затем публикует событие в Kafka.
2. Потребители проекций материализуют модели чтения в PostgreSQL.
3. Аналитические потребители вычисляют метрики, аномалии, дрейф и события алертинга.
4. API читает данные только из PostgreSQL и никогда не читает Kafka напрямую.

Описание топиков Kafka и схемы событий находится в [docs/architecture/event-flow.md](docs/architecture/event-flow.md).

## Локальный запуск

1. Скопируйте `.env.example` в `.env`
2. Установите зависимости через `uv`: `uv sync --extra dev`
3. Рекомендуемый единый запуск: `uv run python scripts/dev_stack.py start`
4. Альтернатива для Windows: `powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1`
5. Альтернатива для Unix: `sh scripts/start-local.sh`

API будет доступен по адресу `http://localhost:8080`, метрики по `/metrics`, документация по `/docs`.

### Единый bootstrap через uv

Для локальной разработки рекомендуется использовать единый bootstrap-скрипт:

```bash
uv run python scripts/dev_stack.py start
```

Что он делает:

- проверяет доступность Docker и `docker compose`;
- создает `.env` из `.env.example`, если файл еще не создан;
- нормализует чувствительные env-переменные в JSON-формат для Pydantic settings;
- поднимает `docker compose up -d --build`;
- ждет готовности `http://localhost:8080/api/v1/health/ready`;
- показывает состояние контейнеров;
- запускает smoke-проверку API и LangGraph execution flow.

Полезные варианты:

- запуск без пересборки: `uv run python scripts/dev_stack.py start --no-build`
- запуск без smoke: `uv run python scripts/dev_stack.py start --skip-smoke`
- отдельная smoke-проверка: `uv run python scripts/dev_stack.py smoke`
- остановка стека: `uv run python scripts/dev_stack.py stop`
- остановка с удалением volumes: `uv run python scripts/dev_stack.py stop --volumes`

### Локальная диагностика Kafka

Для локальной диагностики Kafka есть отдельный toolkit:

```bash
uv run python scripts/kafka_debug.py all
```

Полезные команды:

- `uv run python scripts/kafka_debug.py topics`
- `uv run python scripts/kafka_debug.py groups`
- `uv run python scripts/kafka_debug.py lag`
- `uv run python scripts/kafka_debug.py dlq`
- `uv run python scripts/kafka_debug.py describe-group projection-consumers`
- `uv run python scripts/kafka_debug.py describe-topic agent.executions`

## Запуск тестов

- Полный набор тестов: `uv run pytest`
- Линтеры: `uv run ruff check .`
- Форматирование: `uv run black . && uv run ruff check . --fix`
- Проверка типов: `uv run mypy app tests`

## Docker

- Сборка API-образа: `docker build -f docker/Dockerfile -t workflow-platform:local .`
- Подъем локального стека: `docker compose up --build`

## Деплой через Helm

Helm-чарт расположен в `helm/workflow-platform`.

```bash
helm upgrade --install workflow-platform helm/workflow-platform \
  -f helm/workflow-platform/values-prod.yaml \
  --namespace workflow-platform --create-namespace
```

## Пример выполнения сценария

Примерный сценарий использует три последовательных этапа:

- `planner` декомпозирует цель и формирует план
- `tool-runner` выполняет прикладные шаги
- `reviewer` проверяет результат и формирует финальный ответ

Пример входного запроса находится в `examples/workflow_execution.json`.

### Пример запуска с веткой `validator`

Если нужен дополнительный шаг проверки между `tool_runner` и `reviewer`, передайте
`require_validation: true` во входном payload:

```json
{
  "graph_definition_id": "graph-validator-demo",
  "input_payload": {
    "objective": "Validate rollout plan for a degraded workflow",
    "require_validation": true,
    "context": {
      "environment": "prod",
      "service": "billing-workflow",
      "time_window": "last_15m"
    }
  },
  "metadata": {
    "requested_by": "platform-ops",
    "ticket": "INC-2091"
  }
}
```

В этом режиме граф пройдет путь `planner -> tool_runner -> validator -> reviewer`, а
в итоговом `output_payload` появится поле `validation_summary`.

## Структура репозитория

- `app/` код приложения
- `tests/` модульные и интеграционные тесты
- `alembic/` миграции базы данных
- `docs/` документация MkDocs
- `helm/` Helm chart
- `deploy/` Kubernetes manifests и примеры интеграции
- `scripts/` операционные и вспомогательные скрипты
- `docker/` контейнерные артефакты
- `examples/` примеры входных запросов

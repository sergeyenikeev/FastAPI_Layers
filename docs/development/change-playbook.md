# Playbook изменений

## Назначение

Этот документ помогает быстро понять, какие файлы затрагивать при типовых изменениях и что именно нужно проверить после внесения правок.

Перед началом изменений полезно держать открытыми два справочных документа:

- [Руководство разработчика](guide.md) для общего процесса работы, запуска окружения и правил проекта
- [Справочник по модулям](modules.md) для понимания, какой модуль за что отвечает и какие соседние слои затрагиваются

## Если меняется реестр сущностей

Обычно затрагиваются:

- `app/modules/registry/schemas.py`
- `app/modules/registry/commands.py`
- `app/modules/registry/queries.py`
- `app/modules/registry/api.py`
- `app/projections/projector.py`
- `app/domain/schemas.py`
- `app/db/models.py`
- `tests/unit/test_registry_commands.py`
- `tests/integration/test_api_flow.py`

Проверьте:

- публикуется ли событие;
- материализуется ли проекция;
- видит ли read API новое поле или сущность.

## Если меняется выполнение сценария

Обычно затрагиваются:

- `app/modules/orchestration/schemas.py`
- `app/modules/orchestration/gateway.py`
- `app/modules/orchestration/graph.py`
- `app/modules/orchestration/service.py`
- `app/messaging/topics.py`
- `app/workers.py`
- `tests/integration/test_api_flow.py`
- `tests/integration/test_kafka_flow.py`

Проверьте:

- создается ли `execution.started`;
- публикуются ли step events;
- закрывается ли run в `execution.finished` или `execution.failed`;
- не сломались ли cost и metric events.

## Если меняется projection layer

Обычно затрагиваются:

- `app/projections/projector.py`
- `app/db/models.py`
- `app/domain/schemas.py`
- `tests/integration/test_api_flow.py`
- `tests/integration/test_alerting_flow.py`

Проверьте:

- upsert работает для новых и повторных событий;
- идемпотентность не нарушена;
- read API получает данные из обновленной проекции.

## Если меняется мониторинг

Обычно затрагиваются:

- `app/core/metrics.py`
- `app/modules/monitoring/api.py`
- `app/modules/monitoring/queries.py`
- `app/modules/monitoring/schemas.py`
- `app/modules/monitoring/anomaly.py`
- `app/modules/monitoring/drift.py`
- `docs/operations/monitoring-guide.md`

Проверьте:

- новая метрика видна в `/metrics`;
- summary endpoints корректно агрегируют данные;
- аномалии и дрейф не вызывают лавинообразные ложные срабатывания.

## Если меняется Kafka-контур

Обычно затрагиваются:

- `app/messaging/topics.py`
- `app/messaging/kafka.py`
- `app/workers.py`
- `scripts/create_topics.py`
- `scripts/kafka_debug.py`
- `helm/workflow-platform/values*.yaml`
- `helm/workflow-platform/templates/keda-scaledobject.yaml`
- `tests/integration/test_kafka_flow.py`
- `docs/architecture/event-flow.md`
- `docs/architecture/kafka.md`

Проверьте:

- правильность названий topics и DLQ;
- partition key и consumer group;
- retry policy;
- offset commit после успешной обработки;
- маршрутизацию в DLQ после исчерпания ретраев.
- локальную диагностику через `uv run python scripts/kafka_debug.py all`

## Если меняется аутентификация или RBAC

Обычно затрагиваются:

- `app/core/security.py`
- `app/core/middleware.py`
- `app/api/router.py`
- модульные `api.py`, где появились новые ограничения доступа
- `tests/unit/test_security.py`
- интеграционные тесты на endpoint, чье поведение изменилось

Проверьте:

- API key сценарии;
- JWT сценарии;
- отказ для недостаточных прав;
- наличие аудита для write-операций.

## Если меняется Helm или Kubernetes

Обычно затрагиваются:

- `helm/workflow-platform/values.yaml`
- `helm/workflow-platform/values-dev.yaml`
- `helm/workflow-platform/values-prod.yaml`
- `helm/workflow-platform/templates/*.yaml`
- `deploy/kubernetes/*.yaml`
- `docs/operations/helm-kubernetes.md`
- `docs/operations/deployment-guide.md`

Проверьте:

- шаблоны рендерятся без ошибок;
- probes и env vars согласованы с приложением;
- secret refs указывают на существующие значения;
- KEDA и HPA не конфликтуют по логике масштабирования.

## Если меняется схема данных

Затрагиваются:

- `app/db/models.py`
- `alembic/versions/*`
- `app/domain/schemas.py`
- `app/projections/projector.py`
- тесты на соответствующий read side

Проверьте:

- создание базы с нуля;
- применение миграций поверх существующей схемы;
- совместимость DTO и ORM;
- корректную сериализацию дат, JSON и числовых полей.

## Полезная последовательность проверки

Для большинства изменений достаточно такого порядка:

1. `uv run black .`
2. `uv run ruff check .`
3. `uv run mypy app tests`
4. `uv run pytest`
5. `uv run mkdocs build`

## Когда обязательно обновлять несколько слоев сразу

Нельзя ограничиваться только кодом, если меняется:

- event payload: обновляйте `projector`, tests и docs;
- DTO: обновляйте API, queries, tests и docs;
- Kafka topic: обновляйте workers, scripts, Helm и docs;
- конфиг: обновляйте `.env.example`, chart values, deployment guide и при необходимости compose;
- health logic: обновляйте probes, runbook и monitoring guide.

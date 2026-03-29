# Руководство по API

## Назначение раздела

Этот документ нужен для двух задач:

- быстро понять структуру API и назначение групп ручек;
- удобно тестировать ручки через Swagger на `http://localhost:8080/docs`.

Важно помнить:

- write-операции публикуют события и обычно возвращают `CommandAccepted`;
- read-операции читают только materialized read models из PostgreSQL;
- часть эффектов после write-запроса появляется не мгновенно, а после обработки события projection worker-ом.
- при локальном старте через `uv run python scripts/dev_stack.py start` demo-сущности создаются автоматически, поэтому `GET /api/v1/agents`, `GET /api/v1/models`, `GET /api/v1/graphs`, `GET /api/v1/environments` и `GET /api/v1/deployments` обычно уже возвращают непустой результат.

## Базовый префикс

- `/api/v1`

## Основные маршруты

- `/agents`
- `/models`
- `/graphs`
- `/deployments`
- `/tools`
- `/environments`
- `/executions`
- `/metrics`
- `/metrics/summary`
- `/costs`
- `/anomalies`
- `/drift`
- `/alerts`
- `/audit`
- `/health/live`
- `/health/ready`
- `/health/deep`
- `/metrics` — отдельный Prometheus endpoint без префикса `/api/v1`

## Аутентификация в Swagger

Для тестирования в Swagger нужно сначала авторизоваться.

Поддерживаются два варианта:

- `X-API-Key`
- Bearer JWT

### Самый простой способ для локальной проверки

1. Откройте `http://localhost:8080/docs`
2. Нажмите `Authorize`
3. В схеме `APIKeyHeader` вставьте:

```text
replace-with-api-key
```

4. Нажмите `Authorize`, затем `Close`

Этого достаточно для локального тестирования большинства ручек.

## Как запускать ручки через Swagger

Ниже приведены рекомендуемые последовательности проверки API именно через Swagger UI.

### Вариант 1. Быстрая инициализация справочников

Подходит для первого знакомства с платформой.

Последовательность:

1. `POST /api/v1/graphs`
2. `POST /api/v1/agents`
3. `POST /api/v1/models`
4. `POST /api/v1/environments`
5. `GET /api/v1/graphs`
6. `GET /api/v1/agents`
7. `GET /api/v1/models`
8. `GET /api/v1/environments`

Рекомендуемые payload-ы:

`POST /api/v1/graphs`
```json
{
  "name": "billing-validator-graph",
  "description": "Граф выполнения для проверки деградации платежного сценария",
  "version": "v1",
  "entrypoint": "planner",
  "definition": {
    "nodes": ["planner", "tool_runner", "reviewer"]
  }
}
```

`POST /api/v1/agents`
```json
{
  "name": "billing-ops-agent",
  "description": "Агент сопровождения платежного workflow",
  "owner": "platform-team",
  "version": "v1",
  "runtime_config": {
    "timeout_seconds": 30
  }
}
```

`POST /api/v1/models`
```json
{
  "name": "internal-llm-gateway",
  "provider": "internal",
  "base_url": "https://model-gateway.local",
  "auth_type": "bearer",
  "version": "v1",
  "model_name": "ops-model",
  "context_window": 8192,
  "pricing": {
    "input_per_1k": 0.001,
    "output_per_1k": 0.002
  },
  "is_default": true
}
```

`POST /api/v1/environments`
```json
{
  "name": "prod",
  "description": "Продакшен окружение",
  "labels": {
    "criticality": "high",
    "region": "ru-central"
  }
}
```

### Вариант 2. Полный путь до запуска execution

Подходит для демонстрации полного user flow.

Последовательность:

1. создать graph
2. создать agent
3. создать model
4. создать environment
5. создать deployment
6. запустить execution
7. посмотреть execution и шаги
8. проверить metrics, costs, anomalies, alerts

Ключевой payload для `POST /api/v1/deployments`:
```json
{
  "agent_version_id": "agent-version-id-from-agent-creation",
  "model_version_id": "model-version-id-from-model-creation",
  "environment_id": "environment-id-from-environment-creation",
  "replica_count": 1,
  "configuration": {
    "mode": "production",
    "validation_required": false
  }
}
```

Ключевой payload для `POST /api/v1/executions`:
```json
{
  "deployment_id": "deployment-id-from-previous-step",
  "input_payload": {
    "objective": "Проверить деградацию workflow обработки платежей",
    "service": "billing",
    "time_window": "last_15m"
  },
  "metadata": {
    "requested_by": "swagger-demo",
    "ticket": "INC-1001"
  }
}
```

После ответа `CommandAccepted`:

1. возьмите `entity_id`
2. вызовите `GET /api/v1/executions/{execution_id}`
3. при необходимости обновите запрос через несколько секунд, пока projection worker не материализует read model

### Вариант 3. Запуск execution с веткой validator

Подходит для проверки условной ветки LangGraph.

`POST /api/v1/executions`
```json
{
  "graph_definition_id": "graph-validator-demo",
  "input_payload": {
    "objective": "Проверить рискованное изменение workflow",
    "require_validation": true,
    "context": {
      "environment": "prod",
      "service": "billing-workflow"
    }
  },
  "metadata": {
    "requested_by": "swagger-demo",
    "ticket": "INC-2091"
  }
}
```

Что ожидать:

- execution пойдет по пути `planner -> tool_runner -> validator -> reviewer`
- в `GET /api/v1/executions/{execution_id}` появится `validation_summary`
- в списке шагов появится шаг `validator`

### Вариант 4. Проверка мониторинга и эксплуатационного слоя

Полезная последовательность:

1. `GET /api/v1/health/live`
2. `GET /api/v1/health/ready`
3. `GET /api/v1/health/deep`
4. `GET /api/v1/metrics/summary`
5. `GET /api/v1/costs`
6. `GET /api/v1/anomalies`
7. `GET /api/v1/drift`
8. `GET /api/v1/alerts`
9. `GET /api/v1/audit`

### Вариант 5. Проверка пагинации и фильтрации

Примеры query-параметров, которые удобно тестировать в Swagger:

- `GET /api/v1/agents?page=1&page_size=10&q=billing`
- `GET /api/v1/executions?page=1&page_size=20&status=succeeded`
- `GET /api/v1/metrics?page=1&page_size=20&metric_name=model_latency_ms`
- `GET /api/v1/alerts?page=1&page_size=20&severity=critical&status=open`
- `GET /api/v1/audit?page=1&page_size=20&entity_type=execution_run`

## Описание групп ручек

### Registry

Группа ручек для управления справочными и конфигурационными сущностями платформы:

- агенты;
- модели;
- графы;
- deployment-ы;
- инструменты;
- окружения.

Когда использовать:

- при первичной настройке платформы;
- при публикации нового сценария;
- при сопровождении конфигурации production-среды.

### Orchestration

Группа ручек для запуска и просмотра выполнений.

Когда использовать:

- чтобы запустить новый execution;
- чтобы отследить статус выполнения;
- чтобы посмотреть шаги, результат и ошибку конкретного запуска.

### Monitoring

Группа ручек для health, performance, стоимости, anomalies и drift.

Когда использовать:

- для эксплуатационного мониторинга;
- для разбора деградации;
- для просмотра cost и model-related сигналов.

### Alerting

Группа ручек для чтения алертов.

Когда использовать:

- для просмотра активных или исторических operational сигналов;
- для ручной проверки того, что anomaly/drift pipeline работает корректно.

### Audit

Группа ручек для чтения audit trail.

Когда использовать:

- для расследования изменений;
- для отслеживания запуска команд;
- для проверки связки действий с `correlation_id` и `trace_id`.

## Описание параметров у ручек

Ниже перечислены наиболее важные параметры, которые чаще всего используются в Swagger.

### Общие query-параметры списков

| Параметр | Где используется | Что означает |
| --- | --- | --- |
| `page` | почти все `GET`-списки | номер страницы результатов |
| `page_size` | почти все `GET`-списки | размер страницы |
| `q` | registry list endpoints | строка поиска |
| `status` | executions, alerts | фильтр по статусу |
| `severity` | anomalies, drift, alerts | фильтр по уровню важности |
| `entity_type` | metrics, audit | тип сущности для фильтрации |
| `entity_id` | metrics | идентификатор сущности |
| `metric_name` | metrics | имя конкретной метрики |
| `environment_id` | costs | фильтр по окружению |
| `window_minutes` | metrics summary | окно агрегации в минутах |

### Ключевые body-параметры write-ручек

#### `POST /api/v1/agents`

| Параметр | Обязательный | Назначение |
| --- | --- | --- |
| `name` | да | имя агента |
| `description` | нет | описание агента |
| `owner` | нет | владелец или команда |
| `version` | нет | стартовая версия |
| `graph_definition_id` | нет | связанный graph definition |
| `runtime_config` | нет | конфигурация рантайма |

#### `POST /api/v1/models`

| Параметр | Обязательный | Назначение |
| --- | --- | --- |
| `name` | да | имя model endpoint-а |
| `provider` | да | провайдер модели |
| `base_url` | да | URL endpoint-а |
| `auth_type` | нет | тип авторизации |
| `version` | нет | версия model endpoint-а |
| `model_name` | да | имя модели |
| `context_window` | нет | размер контекста |
| `pricing` | нет | тарифные параметры |

#### `POST /api/v1/deployments`

| Параметр | Обязательный | Назначение |
| --- | --- | --- |
| `agent_version_id` | да | версия агента |
| `model_version_id` | нет | версия модели |
| `environment_id` | нет | существующее окружение |
| `environment_name` | нет | имя окружения |
| `replica_count` | нет | число реплик |
| `configuration` | нет | execution-конфигурация |

#### `POST /api/v1/executions`

| Параметр | Обязательный | Назначение |
| --- | --- | --- |
| `deployment_id` | условно | запуск по deployment-у |
| `graph_definition_id` | условно | прямой запуск по graph definition |
| `input_payload` | нет, но практически нужен | входные данные выполнения |
| `metadata` | нет | служебные атрибуты запуска |

Важно:

- должен быть указан либо `deployment_id`, либо `graph_definition_id`
- для meaningful execution почти всегда нужен `input_payload.objective`

## Описание результатов ручек

### Что возвращают write-ручки

Большинство write-ручек возвращают `CommandAccepted`.

Это означает:

- команда принята API;
- событие опубликовано;
- дальнейшая materialization состояния произойдет асинхронно.

Структура результата:

| Поле | Назначение |
| --- | --- |
| `entity_id` | идентификатор сущности или запуска |
| `event_id` | идентификатор опубликованного события |
| `event_type` | тип события |
| `status` | обычно `accepted` |
| `correlation_id` | идентификатор трассировки запроса |

### Что возвращают read-списки

Списочные ручки возвращают `Page[T]`.

Структура результата:

| Поле | Назначение |
| --- | --- |
| `items` | элементы текущей страницы |
| `total` | общее число элементов |
| `page` | номер страницы |
| `page_size` | размер страницы |

### Что возвращает `GET /api/v1/executions/{execution_id}`

Это одна из самых полезных ручек в Swagger, потому что она показывает итог всего execution flow.

Основные поля результата:

| Поле | Назначение |
| --- | --- |
| `id` | идентификатор запуска |
| `status` | текущий или финальный статус |
| `input_payload` | входные данные выполнения |
| `output_payload` | итоговый результат |
| `error_message` | ошибка, если выполнение завершилось неуспешно |
| `correlation_id` | идентификатор цепочки событий |
| `trace_id` | trace для observability |
| `steps` | список материализованных execution steps |

### Что возвращают health-ручки

`/health/live`, `/health/ready` и `/health/deep` возвращают `HealthSummary`.

Структура результата:

| Поле | Назначение |
| --- | --- |
| `status` | итоговый статус проверки |
| `components` | список проверенных компонентов |

У каждого компонента есть:

| Поле | Назначение |
| --- | --- |
| `component` | имя проверяемого узла |
| `status` | его статус |
| `details` | детали проверки |
| `checked_at` | время проверки |

## Практические советы для Swagger

- сначала всегда авторизуйтесь через `Authorize`
- для write-запросов начинайте с registry-ручек, затем переходите к execution
- после `POST /api/v1/executions` не ждите мгновенного финального результата в том же ответе
- используйте `entity_id` из `CommandAccepted` для следующего чтения
- если read-side еще не обновился, повторите `GET` через несколько секунд
- для проверки ветки `validator` обязательно ставьте `require_validation: true`

## Где смотреть еще

- подробные описания групп и ручек также встроены прямо в Swagger `/docs`
- operational-контекст описан в [docs/operations/monitoring-guide.md](operations/monitoring-guide.md)
- developer-процесс — в [docs/development/guide.md](development/guide.md)

# Архитектурные паттерны и их применение

## Назначение документа

Этот документ подробно описывает, какие архитектурные и прикладные паттерны проектирования используются в проекте, где именно они реализованы в коде и зачем они выбраны. Цель документа не только перечислить шаблоны, но и показать, как они работают вместе в рамках одной production-ready платформы.

## Архитектурный уровень

### 1. Modular Monolith

Базовый архитектурный стиль проекта — модульный монолит. Система запускается как одно приложение, но внутри уже разделена на устойчивые функциональные области.

Где используется:

- [app/modules/registry](d:/p/FastAPI/FastAPI_Layers/app/modules/registry)
- [app/modules/orchestration](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration)
- [app/modules/monitoring](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring)
- [app/modules/alerting](d:/p/FastAPI/FastAPI_Layers/app/modules/alerting)
- [app/modules/audit](d:/p/FastAPI/FastAPI_Layers/app/modules/audit)
- [app/projections](d:/p/FastAPI/FastAPI_Layers/app/projections)
- [app/api/router.py](d:/p/FastAPI/FastAPI_Layers/app/api/router.py)

Как это проявляется:

- каждый модуль имеет свои `api.py`, `commands.py`, `queries.py`, `schemas.py`;
- границы модулей проходят по доменным обязанностям, а не по техническим слоям;
- модуль может быть позже вынесен в отдельный сервис без полного переписывания предметной логики.

Зачем выбран:

- ускоряет старт разработки;
- уменьшает операционную сложность по сравнению с набором микросервисов;
- сохраняет дисциплину границ и готовность к последующему split.

Trade-off:

- границы модулей соблюдаются организационно и кодом, но процесс остается общим;
- при росте нагрузки самые горячие модули придется выносить в отдельные рантаймы.

### 2. Bounded Context

Внутри модульного монолита используются ограниченные контексты. Это паттерн из Domain-Driven Design, который помогает не смешивать разные смыслы одних и тех же сущностей.

Где используется:

- `registry` отвечает за реестр сущностей и их жизненный цикл;
- `orchestration` отвечает за выполнение графов и шагов;
- `monitoring` отвечает за метрики, anomaly detection и drift detection;
- `alerting` отвечает за dedupe, cooldown и dispatch уведомлений;
- `audit` отвечает за трассируемость действий.

Как это проявляется:

- одни и те же идентификаторы могут жить в разных контекстах, но смысл операций и API у них различается;
- write-side и read-side завязаны на разные use cases.

### 3. CQRS

Проект реализует Command Query Responsibility Segregation.

Где используется:

- write-side: [app/modules/registry/commands.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/commands.py), [app/modules/orchestration/service.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/service.py)
- read-side: [app/modules/registry/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/queries.py), [app/modules/orchestration/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/queries.py), [app/modules/monitoring/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/queries.py)
- materialization слоя чтения: [app/projections/projector.py](d:/p/FastAPI/FastAPI_Layers/app/projections/projector.py)

Как это работает:

- команды не пишут напрямую итоговые read models;
- команда публикует событие в Kafka;
- projection consumers обновляют PostgreSQL read model;
- API читает только PostgreSQL projections, а не Kafka.

Зачем выбран:

- write-path и read-path можно развивать независимо;
- легче масштабировать поток обработки событий и поток чтения;
- проще поддерживать auditability и replay-мышление.

Trade-off:

- появляется eventual consistency;
- нужно отдельно проектировать проекции, идемпотентность и компенсацию out-of-order событий.

### 4. Event-Driven Architecture

Система построена вокруг событийного backbone на Kafka.

Где используется:

- [app/messaging/topics.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/topics.py)
- [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py)
- [app/workers.py](d:/p/FastAPI/FastAPI_Layers/app/workers.py)
- [app/domain/events.py](d:/p/FastAPI/FastAPI_Layers/app/domain/events.py)

Как это проявляется:

- доменные изменения публикуются как события;
- аналитические и projection workers подписаны на разные топики;
- один и тот же факт может быть использован несколькими независимыми потребителями.

Зачем выбран:

- слабая связанность между write-side, monitoring, alerting и read-side;
- естественная точка интеграции для внешних систем;
- удобный путь к асинхронному масштабированию.

### 5. Event Sourcing-lite

Полноценный event sourcing здесь не реализован, но проект использует близкий по духу подход: события являются главным источником асинхронного обновления проекций.

Где используется:

- команды создают `EventEnvelope`;
- projections материализуют таблицы из событий;
- DLQ хранит неуспешно обработанные события как отдельные envelopes.

Почему это важно:

- история действий не теряется на уровне transport-контрактов;
- можно диагностировать, какой именно факт не материализовался в read model;
- audit и event flow естественно увязаны.

Ограничение:

- система не восстанавливает всё состояние исключительно replay-ем Kafka;
- PostgreSQL остается основным источником read state.

## Паттерны интеграции и инфраструктуры

### 6. Message Envelope

Все события заворачиваются в единый envelope.

Где используется:

- [app/domain/events.py](d:/p/FastAPI/FastAPI_Layers/app/domain/events.py)

Поля envelope:

- `event_id`
- `event_version`
- `event_type`
- `timestamp`
- `correlation_id`
- `trace_id`
- `source`
- `entity_id`
- `payload`
- `metadata`

Зачем выбран:

- обеспечивает единообразие событий по всем топикам;
- позволяет строить tracing, audit и диагностику без знания конкретного payload;
- упрощает DLQ и generic consumers.

### 7. Idempotent Consumer

Для consumer layer используется паттерн идемпотентного потребителя.

Где используется:

- [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py)
- таблица `processed_events` в [app/db/models.py](d:/p/FastAPI/FastAPI_Layers/app/db/models.py)

Как это работает:

- перед обработкой события consumer проверяет, было ли оно уже обработано этим `consumer_group`;
- после успешной обработки событие записывается в `processed_events`;
- повторная доставка не ломает read model и не вызывает повторных эффектов.

Зачем выбран:

- Kafka не гарантирует exactly-once для всей бизнес-логики;
- retries и повторные доставки в распределенной системе неизбежны;
- это обязательный паттерн для безопасных проекций и аналитических consumers.

### 8. Retry + Dead Letter Queue

Неуспешная обработка события реализована через retries и DLQ.

Где используется:

- [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py)
- [app/messaging/topics.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/topics.py)

Как это работает:

- consumer делает несколько попыток обработки;
- если все попытки исчерпаны, сообщение заворачивается в `DeadLetterEnvelope`;
- затем оно публикуется в соответствующий `.dlq` topic.

Зачем выбран:

- система не застревает навсегда на одном “ядовитом” сообщении;
- можно отделить эксплуатационную диагностику от горячего пути обработки;
- DLQ создает понятную operational surface для поддержки.

### 9. Composition Root

Все основные зависимости собираются в одном месте.

Где используется:

- [app/runtime.py](d:/p/FastAPI/FastAPI_Layers/app/runtime.py)

Что именно собирается:

- publisher;
- command/query services;
- health service;
- alerting service;
- detector services;
- projector;
- task management для background workflow.

Зачем выбран:

- зависимости создаются централизованно;
- проще тестировать приложение заменой `publisher` на `InMemoryPublisher`;
- модульная логика остается независимой от деталей сборки.

### 10. Dependency Injection

В проекте используется не контейнерная, а явная dependency injection.

Где используется:

- `AppRuntime` передает зависимости сервисам;
- `RegistryCommandService` получает `publisher` и `audit_service`;
- `ExecutionCommandService` получает `publisher`, `audit_service`, `model_gateway`, `task_spawner`;
- `AlertingService` получает `publisher` и `settings`.

Почему это важно:

- сервисы слабо зависят от конкретных реализаций;
- тесты могут подменять зависимости без тяжелого monkey patching;
- логика остается ближе к чистым application services.

### 11. Ports and Adapters

Проект использует подход, близкий к Hexagonal Architecture.

Где используется:

- порт публикации: `PublisherProtocol` в [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py)
- адаптер Kafka: `EventPublisher`
- тестовый адаптер: `InMemoryPublisher`
- внешний модельный адаптер: [app/modules/orchestration/gateway.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/gateway.py)

Как это проявляется:

- прикладные сервисы не знают, публикуются события в Kafka или в память;
- orchestration layer не знает деталей конкретного LLM-provider, он работает через `ModelGateway`.

Зачем выбран:

- упрощает тестирование;
- снижает связность с внешними системами;
- готовит код к замене транспортов и внешних провайдеров.

### 12. Gateway / Adapter

Для вызова внешнего model endpoint используется паттерн Gateway.

Где используется:

- [app/modules/orchestration/gateway.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/gateway.py)

Что делает gateway:

- формирует HTTP-вызов к внешнему endpoint;
- скрывает детали transport-формата;
- рассчитывает latency, token usage и cost;
- содержит fallback-механику для локальной и тестовой среды.

Зачем выбран:

- orchestration graph не должен знать детали HTTP-интеграции;
- можно позднее заменить реализацию gateway на другой provider или SDK;
- диагностика и fallback находятся в одном месте.

## Паттерны прикладной логики

### 13. Service Layer

Основная прикладная логика вынесена в application services.

Где используется:

- [app/modules/registry/commands.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/commands.py)
- [app/modules/registry/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/queries.py)
- [app/modules/orchestration/service.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/service.py)
- [app/modules/alerting/service.py](d:/p/FastAPI/FastAPI_Layers/app/modules/alerting/service.py)

Зачем выбран:

- роутеры остаются тонкими;
- бизнес-операции сосредоточены в отдельных классах;
- проще покрывать unit-тестами и переиспользовать сценарии.

### 14. Command Pattern

Командный стиль особенно явно выражен в write-side.

Где используется:

- [app/modules/registry/commands.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/commands.py)
- [app/modules/orchestration/service.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/service.py)

Как это проявляется:

- методы `create_agent`, `update_agent`, `delete_agent`, `create_execution` и подобные описывают отдельные команды;
- команда инкапсулирует намерение и приводит к публикации события;
- результатом команды является `CommandAccepted`, а не сразу готовый read model.

### 15. Query Object / Query Service

Чтение реализовано отдельными query-сервисами.

Где используется:

- [app/modules/registry/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/registry/queries.py)
- [app/modules/orchestration/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/queries.py)
- [app/modules/monitoring/queries.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/queries.py)

Зачем выбран:

- логика чтения не смешивается с командами;
- проще оптимизировать read-side отдельно;
- API остается тонким прокси к query services.

### 16. Factory

В системе есть несколько локальных фабрик.

Где используется:

- [app/workers.py](d:/p/FastAPI/FastAPI_Layers/app/workers.py) — `build_workers`
- [app/modules/monitoring/anomaly.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/anomaly.py) — `build_default_anomaly_detectors`
- [app/modules/monitoring/drift.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/drift.py) — `build_default_drift_detectors`

Что дают фабрики:

- централизуют правила сборки набора объектов;
- позволяют менять конфигурацию набора без переписывания потребителей;
- хорошо подходят для pluggable подсистем.

### 17. Strategy

Паттерн Strategy используется в anomaly detection и drift detection.

Где используется:

- `AnomalyDetector` protocol и реализации в [app/modules/monitoring/anomaly.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/anomaly.py)
- `DriftDetector` protocol и реализации в [app/modules/monitoring/drift.py](d:/p/FastAPI/FastAPI_Layers/app/modules/monitoring/drift.py)

Реализации:

- `ThresholdRuleDetector`
- `RollingStdDetector`
- `ZScoreDetector`
- `PSIDetector`
- `JensenShannonDetector`

Зачем выбран:

- алгоритмы обнаружения можно комбинировать;
- набор детекторов можно менять без переписывания orchestration и workers;
- удобно строить pluggable monitoring architecture.

### 18. State Machine

Workflow исполнения построен как конечный автомат.

Где используется:

- [app/modules/orchestration/graph.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/graph.py)

Как это проявляется:

- `StateGraph` описывает узлы и переходы;
- `START` и `END` задают точки входа и завершения;
- `add_conditional_edges(...)` реализует условную маршрутизацию после `tool_runner`.

Зачем выбран:

- workflow читается как явный граф, а не как запутанная цепочка `if/else`;
- легче добавлять новые узлы и ветви;
- исполнение естественно сочетается с step-level tracing.

### 19. Workflow / Pipeline

Кроме состояния, orchestration реализует и pipeline-подход: данные последовательно проходят через независимые стадии.

Где используется:

- `planner -> tool_runner -> validator -> reviewer` в [app/modules/orchestration/graph.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/graph.py)

Почему это полезно:

- шаги можно независимо наблюдать, тестировать и расширять;
- pipeline легко транслируется в step events;
- поведение остается предсказуемым для мониторинга и аудита.

### 20. Template Method

В consumer processing используется паттерн Template Method.

Где используется:

- [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py), класс `BaseConsumerWorker`

Как это устроено:

- общий алгоритм обработки сообщения зафиксирован в `_process_record`;
- конкретная бизнес-логика передается через `handler`;
- общий шаблон включает идемпотентность, retries, commit offset и DLQ.

Почему это полезно:

- все consumers следуют одному безопасному жизненному циклу;
- уменьшается дублирование критичной инфраструктурной логики;
- новый consumer проще добавить и труднее сделать небезопасным.

### 21. Facade

`AppRuntime` частично работает как фасад над основными сервисами системы.

Где используется:

- [app/runtime.py](d:/p/FastAPI/FastAPI_Layers/app/runtime.py)

Что он скрывает:

- создание publisher;
- сборку detectors;
- wiring command/query services;
- управление background tasks.

Почему это полезно:

- верхний слой приложения получает одну понятную точку доступа;
- снижается сложность startup/shutdown логики;
- легче организовать тестовый runtime.

### 22. Fallback

В интеграции с моделью используется fallback-поведение.

Где используется:

- [app/modules/orchestration/gateway.py](d:/p/FastAPI/FastAPI_Layers/app/modules/orchestration/gateway.py)

Как это работает:

- если внешний endpoint недоступен, используется локально синтезированный ответ;
- orchestration не падает только из-за отсутствия внешней модели в dev/test сценарии.

Зачем выбран:

- упрощает локальную разработку;
- делает CI стабильнее;
- сохраняет единый контракт ответа gateway.

## Паттерны хранения и доступа к данным

### 23. Repository-lite

Полноценный rich repository layer в проекте не построен, но локальный репозиторный паттерн используется для общих операций чтения.

Где используется:

- [app/db/repositories.py](d:/p/FastAPI/FastAPI_Layers/app/db/repositories.py)

Что делает:

- выносит общую пагинацию в одну reusable функцию `paginate_query`;
- предотвращает дублирование одинаковой инфраструктурной логики по query services.

Почему это именно repository-lite:

- основная доменная логика чтения находится в query services;
- отдельные aggregate repositories пока не выделены.

### 24. Upsert Projection

Read-side строится через upsert-проекции.

Где используется:

- [app/projections/projector.py](d:/p/FastAPI/FastAPI_Layers/app/projections/projector.py)

Как это работает:

- на каждый `event_type` есть свой обработчик;
- проекция обновляет существующую запись или создает новую;
- для out-of-order событий используются безопасные деградации FK и placeholder-объекты.

Почему это важно:

- Kafka не гарантирует идеальный межтопиковый порядок;
- read-side должен выдерживать асинхронность, ретраи и переигровку событий.

## Паттерны надежности и эксплуатации

### 25. Observability-first

Это не один паттерн, а проектный принцип, но он реализован вполне конкретными шаблонами.

Где используется:

- `correlation_id` и `trace_id` в envelope;
- structured logging;
- Prometheus metrics;
- OpenTelemetry spans;
- step-level telemetry;
- Kafka lag metrics.

Файлы:

- [app/core/logging.py](d:/p/FastAPI/FastAPI_Layers/app/core/logging.py)
- [app/core/metrics.py](d:/p/FastAPI/FastAPI_Layers/app/core/metrics.py)
- [app/core/observability.py](d:/p/FastAPI/FastAPI_Layers/app/core/observability.py)
- [app/messaging/kafka.py](d:/p/FastAPI/FastAPI_Layers/app/messaging/kafka.py)

Зачем это сделано:

- любой командный и событийный путь можно проследить end-to-end;
- проще разбирать инциденты, лаг, пропавшие проекции и аномалии;
- эксплуатационная диагностика становится частью архитектуры, а не внешней надстройкой.

### 26. Dedupe + Cooldown

В alerting используется паттерн дедупликации повторяющихся сигналов с временным окном подавления.

Где используется:

- [app/modules/alerting/service.py](d:/p/FastAPI/FastAPI_Layers/app/modules/alerting/service.py)

Как это работает:

- строится `dedupe_key`;
- ищется существующий alert;
- если cooldown еще не истек, новый alert не отправляется повторно.

Зачем выбран:

- защищает операторов от alert storm;
- снижает шум без потери сущности инцидента.

## Как паттерны работают вместе

Система не использует один “главный” паттерн. Архитектура построена как сочетание нескольких уровней:

1. `Modular Monolith` задает форму репозитория и приложения.
2. `Bounded Context` задает смысловые границы модулей.
3. `CQRS` разделяет запись и чтение.
4. `Event-Driven Architecture` обеспечивает транспорт и слабую связанность.
5. `Message Envelope`, `Idempotent Consumer`, `Retry + DLQ` делают событийный слой безопасным.
6. `Service Layer`, `Command`, `Query Service`, `Factory`, `Strategy` формируют прикладной код.
7. `State Machine` и `Workflow` задают оркестрацию исполнения.
8. `Composition Root` и `Dependency Injection` удерживают систему управляемой.

Именно это сочетание дает нужные свойства платформы:

- быстрый запуск новых сценариев;
- управляемое развитие без раннего распила на микросервисы;
- хорошую наблюдаемость;
- контролируемую eventual consistency;
- готовность к дальнейшему выделению сервисов и scaling по ролям.

## Что сознательно не использовано как отдельный паттерн

Ниже перечислены подходы, которые здесь либо применены частично, либо пока не оформлены как отдельный слой:

- полноценный Outbox pattern;
- полноценный Saga orchestrator между независимыми сервисами;
- rich domain model с aggregate roots и domain invariants внутри самих сущностей;
- full event sourcing как единственный источник состояния.

Это осознанный выбор в пользу более прагматичной архитектуры первого production-ready этапа.

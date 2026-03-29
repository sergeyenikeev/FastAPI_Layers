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

## Сводная таблица для архитектурного ревью

Эта таблица нужна как быстрый инструмент для обсуждения решений на архитектурном ревью, планировании и приоритизации технических инвестиций.

| Паттерн | Преимущества | Риски и ограничения | Стоимость внедрения |
| --- | --- | --- | --- |
| Modular Monolith | Быстрый старт, меньше операционной сложности, хорошая база для дальнейшего split | Требует дисциплины границ, иначе превращается в связанный монолит | Низкая на старте, средняя по мере роста |
| Bounded Context | Уменьшает смысловую связанность, помогает масштабировать командную разработку | Требует архитектурной дисциплины и общей терминологии | Средняя |
| CQRS | Позволяет отдельно развивать write-side и read-side, удобен для high-read нагрузок | Добавляет eventual consistency и отдельный слой проекций | Средняя |
| Event-Driven Architecture | Снижает связанность модулей, упрощает интеграции и масштабирование consumers | Усложняет отладку, требует зрелой observability и четких контрактов | Средняя или высокая в зависимости от зрелости платформы |
| Message Envelope | Делает события единообразными, упрощает tracing, audit и DLQ | Требует строго поддерживать совместимость схемы envelope | Низкая |
| Idempotent Consumer | Защищает от дублей и ретраев, стабилизирует read-side | Нужны доп. таблицы и careful handling для processed state | Средняя |
| Retry + DLQ | Не блокирует поток на “ядовитых” событиях, создает понятную operational surface | Без процессов разбора DLQ можно накопить “тихие” ошибки | Средняя |
| Composition Root | Централизует wiring, упрощает тестирование и замену зависимостей | При росте может стать перегруженной точкой сборки | Низкая |
| Dependency Injection | Повышает тестируемость и снижает связанность сервисов с реализациями | При неаккуратном применении делает граф зависимостей трудно читаемым | Низкая |
| Ports and Adapters | Изолирует доменную логику от транспорта и внешних систем | Увеличивает число абстракций и файлов | Средняя |
| Gateway / Adapter | Локализует интеграцию с внешними провайдерами, упрощает fallback и замену backend | Есть риск превратить gateway в “толстый” слой со смешанной логикой | Низкая или средняя |
| Service Layer | Делает API тонким, концентрирует прикладные сценарии в одном месте | Есть риск разрастания сервисов в procedural god-objects | Низкая |
| Command Pattern | Хорошо выражает намерение и write use cases, хорошо ложится на event flow | Может привести к избытку мелких команд без явной пользы | Низкая |
| Query Service | Делает read-side прозрачным и удобным для оптимизации | Легко получить дублирование фильтров и пагинации без общей базы | Низкая |
| Factory | Централизует сборку наборов объектов, удобна для pluggable subsystems | Может скрывать слишком много конфигурации и усложнять отладку | Низкая |
| Strategy | Идеален для pluggable detection logic и сменяемых алгоритмов | При большом числе стратегий усложняет выбор, конфиг и интерпретацию результатов | Низкая или средняя |
| State Machine | Делает workflow явным, расширяемым и удобным для step-level наблюдаемости | Для очень простых сценариев может быть тяжелее линейного кода | Средняя |
| Workflow / Pipeline | Хорошо раскладывает исполнение на независимые стадии, упрощает тесты и telemetry | При сильной зависимости шагов pipeline может стать хрупким | Средняя |
| Template Method | Позволяет стандартизировать жизненный цикл consumers и уменьшить дублирование | Ошибка в базовом шаблоне влияет сразу на все реализации | Средняя |
| Facade | Упрощает верхнему слою доступ к системе, снижает когнитивную нагрузку | Есть риск превращения фасада в перегруженный “универсальный объект” | Низкая |
| Fallback | Улучшает локальную разработку и деградацию при сбоях внешних зависимостей | Может скрывать реальные проблемы production-интеграции, если fallback слишком “мягкий” | Низкая |
| Repository-lite | Убирает повторяющуюся инфраструктурную логику доступа к данным | Не заменяет полноценную модель aggregate repository там, где она реально нужна | Низкая |
| Upsert Projection | Хорошо подходит для event-driven materialization read models | Требует careful handling out-of-order и nullable/FK edge cases | Средняя |
| Observability-first | Сильно ускоряет диагностику, ревью инцидентов и развитие платформы | Повышает стоимость внедрения и сопровождения на старте | Средняя или высокая |
| Dedupe + Cooldown | Снижает alert storm и шум для операторов | Неправильные ключи дедупликации могут прятать важные сигналы | Низкая или средняя |

## Что сознательно не использовано как отдельный паттерн

Ниже перечислены подходы, которые здесь либо применены частично, либо пока не оформлены как отдельный слой:

- полноценный Outbox pattern;
- полноценный Saga orchestrator между независимыми сервисами;
- rich domain model с aggregate roots и domain invariants внутри самих сущностей;
- full event sourcing как единственный источник состояния.

Это осознанный выбор в пользу более прагматичной архитектуры первого production-ready этапа.

## Архитектурная roadmap по пока неиспользованным паттернам

Ниже приведена таблица паттернов, которые осознанно не внедрены на текущем этапе. Это не “упущения”, а отложенные решения, для которых пока нет достаточного operational или product pressure.

| Паттерн | Текущее решение | Почему пока не внедрен | Когда стоит внедрять | На что смотреть заранее |
| --- | --- | --- | --- | --- |
| Outbox Pattern | События публикуются приложением напрямую в Kafka после обработки команды | Текущий write-path проще, дешевле в сопровождении и быстрее для старта. Дополнительная таблица outbox, relay-процесс и транзакционная связка пока дали бы больше сложности, чем пользы | Когда потребуется более строгая атомарность между записью в БД и публикацией события, особенно при появлении синхронных write-моделей внутри транзакции | рост числа “запись произошла, а событие не ушло”, требования к exactly-once семантике бизнеса, появление критичных side effects |
| Saga / Process Manager | Межмодульная координация в основном строится на независимых consumers и eventual consistency | Пока нет длинных бизнес-транзакций через несколько независимых сервисов с компенсациями. Внутри modular monolith это решается проще | Когда orchestration, billing, deployment и внешние интеграции будут разнесены по разным сервисам и появятся распределенные rollback-сценарии | рост числа компенсационных операций, появление “полусобранных” процессов, необходимость формализованной оркестрации между сервисами |
| Rich Domain Model / Aggregate Root | Предметная логика сосредоточена в application services и projection logic, а ORM-модели остаются относительно простыми | Для текущего этапа важнее прозрачный сервисный слой и скорость развития. Полноценная доменная модель потребует более жесткой формализации инвариантов и lifecycle aggregate | Когда бизнес-правила внутри сущностей станут существенно сложнее, а инварианты перестанут удобно жить в сервисах | дублирование одинаковых проверок в нескольких сервисах, рост числа связанных инвариантов вокруг одной сущности, усложнение правил обновления |
| Full Event Sourcing | Kafka-события уже играют важную роль, но PostgreSQL остается основным persisted read state, а не только материализованной проекцией | Полный event sourcing повышает сложность схем версионирования, replay, snapshotting и миграций. Для платформы первого этапа это избыточно | Когда потребуется гарантированный исторический replay состояния как основная operational capability, а не только диагностика событий | потребность восстанавливать состояние исключительно из event log, требования к timeline reconstruction, необходимость моделировать состояние через snapshots |
| Event Store как отдельный слой | Сейчас используется Kafka как backbone и PostgreSQL как state/read store | Отдельный event store добавил бы еще один критический инфраструктурный компонент без немедленной ценности | Когда потребуется долгосрочное хранение, богатый replay и версионирование событий как первичная архитектурная ось | рост потребности в историческом анализе по событиям, сложные replay-сценарии, требования compliance к неизменяемому event log |
| Circuit Breaker | Для внешнего model endpoint есть fallback, но нет полноценного circuit breaker-состояния | Fallback уже покрывает dev/test и базовую деградацию. Полный circuit breaker нужен, когда есть частые деградирующие внешние зависимости и важно защитить их от шторма ретраев | Когда внешний endpoint станет реально нестабильным продакшен-зависимым звеном с высокой ценой перегрузки | повторяющиеся timeouts, bursts ошибок 5xx, cascading failures из-за внешнего провайдера |
| Bulkhead Isolation | Роли workers уже разделены, но нет более глубокого ресурсного bulkhead внутри самого приложения | Текущего разделения на API, projection, analytics и alerts достаточно для первого production-ready контура | Когда внутри одной роли появятся конкурирующие тяжелые подзадачи с риском взаимной деградации | конкуренция за CPU/память между типами workloads, влияние аналитики на projection latency, неустойчивое время обработки |
| Inbox Pattern для inbound-команд | Входящие команды обрабатываются напрямую через API и Kafka event flow | Пока входная нагрузка и количество интеграционных источников позволяют обойтись без отдельного persisted inbox для dedupe и replay | Когда появятся внешние источники команд с гарантированной повторной доставкой и жесткими требованиями к dedupe на входе | дублирующиеся внешние запросы, webhook storm, необходимость хранить входные команды до фактической обработки |
| Schema Registry / Avro / Protobuf Contracts | Контракты событий сейчас унифицированы через Pydantic envelope и JSON payload | Для текущей команды и скорости итерации JSON проще, прозрачнее и дешевле по изменениям | Когда число producers/consumers вырастет, а совместимость контрактов между командами станет критичной | частые incompatible changes payload, внешний обмен событиями с другими командами, потребность в строгой эволюции схем |
| Rule Engine для alerting и detection | Сейчас правила задаются кодом через набор detector strategies и alert service | Кодовая конфигурация пока проще и надежнее. Вынос в отдельный rule engine оправдан только при высокой изменчивости правил со стороны операций | Когда операционная команда захочет часто менять правила без выпуска кода | рост числа детекторов и исключений, частые ручные правки порогов, запросы на self-service настройку правил |

### Как читать эту roadmap

- Если паттерн находится в таблице, это не означает, что архитектура “неполная”.
- Таблица показывает осознанные точки роста, а не долги, которые нужно срочно закрыть.
- Возвращаться к этим паттернам стоит только тогда, когда текущая архитектура начинает мешать надежности, скорости изменений или эксплуатации.

## Короткая матрица по приоритету паттернов

Эта матрица нужна для быстрых архитектурных обсуждений на ревью, планировании и приоритизации технических задач. Она не заменяет подробные разделы выше, а помогает быстро понять, какие решения обязательны уже сейчас, какие важны при росте нагрузки, а какие в первую очередь помогают команде быстрее и безопаснее разрабатывать систему.

| Категория | Паттерны | Почему именно они |
| --- | --- | --- |
| Критичны для production | `CQRS`, `Event-Driven Architecture`, `Message Envelope`, `Idempotent Consumer`, `Retry + DLQ`, `Observability-first`, `Dedupe + Cooldown`, `Composition Root` | Эти паттерны обеспечивают надежность горячего пути, устойчивость к повторной доставке, диагностику инцидентов, читаемый operational surface и предсказуемую сборку зависимостей в рантайме. Без них система быстро начинает терять события, шуметь алертами или становиться трудной в сопровождении. |
| Важны для масштабирования | `Modular Monolith`, `Bounded Context`, `Ports and Adapters`, `Gateway / Adapter`, `Workflow / Pipeline`, `Upsert Projection`, `Fallback` | Эти решения позволяют отделять зоны ответственности, выносить части системы в отдельные рантаймы, масштабировать обработку событий и снижать связанность между модулями и внешними интеграциями. Они особенно полезны, когда растет число команд, окружений и сценариев нагрузки. |
| Важны для удобства разработки и тестирования | `Dependency Injection`, `Service Layer`, `Command Pattern`, `Query Service`, `Factory`, `Strategy`, `Template Method`, `Facade`, `Repository-lite`, `State Machine` | Эти паттерны упрощают локальную разработку, изоляцию зависимостей, модульное тестирование и чтение кода. Они делают проект предсказуемым для новых разработчиков и уменьшают стоимость изменений в прикладной логике. |

### Как пользоваться матрицей

- Если обсуждается надежность, эксплуатация или готовность к продакшену, в первую очередь смотрите на строку `Критичны для production`.
- Если обсуждается рост нагрузки, дробление монолита или увеличение числа интеграций, ориентируйтесь на строку `Важны для масштабирования`.
- Если задача касается скорости разработки, качества ревью и тестируемости, полезнее всего строка `Важны для удобства разработки и тестирования`.

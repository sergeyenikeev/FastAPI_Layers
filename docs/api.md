# Руководство по API

## Базовый префикс

- `/api/v1`

## Основные маршруты

- `/agents`
- `/models`
- `/graphs`
- `/deployments`
- `/executions`
- `/metrics`
- `/metrics/summary`
- `/costs`
- `/anomalies`
- `/drift`
- `/alerts`
- `/health/live`
- `/health/ready`
- `/health/deep`

## Аутентификация

- `X-API-Key` для сценариев первичной инициализации и автоматизации
- Bearer JWT для ролевого доступа

## Роли доступа

- `admin`
- `operator`
- `viewer`

## Поведение API

- Операции записи возвращают `CommandAccepted`
- Операции чтения получают данные только из проекций PostgreSQL
- Пагинация реализована через `page` и `page_size`
- OpenAPI доступен по пути `/docs`

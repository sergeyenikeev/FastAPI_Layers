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

## Kubernetes

```bash
helm upgrade --install workflow-platform helm/workflow-platform \
  -f helm/workflow-platform/values-prod.yaml \
  --namespace workflow-platform --create-namespace
```

## Миграции

- При локальном запуске через Docker выполняется `uv run alembic upgrade head`
- В Helm используется `Job` hook на `pre-install/pre-upgrade`

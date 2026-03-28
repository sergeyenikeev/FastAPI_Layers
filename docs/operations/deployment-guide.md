# Руководство по деплою

## Локальный запуск

```bash
cp .env.example .env
make install
docker compose up --build
```

## Kubernetes

```bash
helm upgrade --install workflow-platform helm/workflow-platform \
  -f helm/workflow-platform/values-prod.yaml \
  --namespace workflow-platform --create-namespace
```

## Миграции

- При локальном запуске через Docker выполняется `alembic upgrade head`
- В Helm используется `Job` hook на `pre-install/pre-upgrade`

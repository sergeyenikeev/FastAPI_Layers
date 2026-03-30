#!/bin/sh
set -eu

python scripts/create_topics.py || true
alembic upgrade head

APP_COMPONENT="${APP_COMPONENT:-gateway}"

case "$APP_COMPONENT" in
  gateway)
    APP_MODULE="app.main:app"
    ;;
  registry)
    APP_MODULE="app.services.registry_api:app"
    ;;
  orchestration)
    APP_MODULE="app.services.orchestration_api:app"
    ;;
  orchestration-query)
    APP_MODULE="app.services.orchestration_query_api:app"
    ;;
  monitoring)
    APP_MODULE="app.services.monitoring_api:app"
    ;;
  alerting)
    APP_MODULE="app.services.alerting_api:app"
    ;;
  audit)
    APP_MODULE="app.services.audit_api:app"
    ;;
  *)
    echo "Unknown APP_COMPONENT: $APP_COMPONENT" >&2
    exit 1
    ;;
esac

uvicorn "$APP_MODULE" --host 0.0.0.0 --port 8080

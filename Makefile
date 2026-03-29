UV ?= uv
APP_MODULE ?= app.main:app

.PHONY: install dev lint format typecheck test run worker migrations-upgrade migrations-revision docs serve-docs compose-up compose-down bootstrap-local smoke-local stop-local kafka-topics kafka-groups kafka-lag kafka-dlq

install:
	$(UV) sync --extra dev

dev:
	$(UV) run uvicorn $(APP_MODULE) --reload --host 0.0.0.0 --port 8080

lint:
	$(UV) run ruff check .

format:
	$(UV) run black .
	$(UV) run ruff check . --fix

typecheck:
	$(UV) run mypy app tests

test:
	$(UV) run pytest

run:
	$(UV) run uvicorn $(APP_MODULE) --host 0.0.0.0 --port 8080

worker:
	$(UV) run python -m app.worker

migrations-upgrade:
	$(UV) run alembic upgrade head

migrations-revision:
	$(UV) run alembic revision --autogenerate -m "$(m)"

docs:
	$(UV) run mkdocs build

serve-docs:
	$(UV) run mkdocs serve

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v

bootstrap-local:
	$(UV) run python scripts/dev_stack.py start

smoke-local:
	$(UV) run python scripts/dev_stack.py smoke

stop-local:
	$(UV) run python scripts/dev_stack.py stop

kafka-topics:
	$(UV) run python scripts/kafka_debug.py topics

kafka-groups:
	$(UV) run python scripts/kafka_debug.py groups

kafka-lag:
	$(UV) run python scripts/kafka_debug.py lag

kafka-dlq:
	$(UV) run python scripts/kafka_debug.py dlq

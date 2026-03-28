UV ?= uv
APP_MODULE ?= app.main:app

.PHONY: install dev lint format typecheck test run worker migrations-upgrade migrations-revision docs serve-docs compose-up compose-down

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

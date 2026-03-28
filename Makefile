PYTHON ?= python
PIP ?= $(PYTHON) -m pip
APP_MODULE ?= app.main:app

.PHONY: install dev lint format typecheck test run worker migrations-upgrade migrations-revision docs serve-docs compose-up compose-down

install:
	$(PIP) install -e .[dev]

dev:
	uvicorn $(APP_MODULE) --reload --host 0.0.0.0 --port 8080

lint:
	ruff check .

format:
	black .
	ruff check . --fix

typecheck:
	mypy app tests

test:
	pytest

run:
	uvicorn $(APP_MODULE) --host 0.0.0.0 --port 8080

worker:
	$(PYTHON) -m app.worker

migrations-upgrade:
	alembic upgrade head

migrations-revision:
	alembic revision --autogenerate -m "$(m)"

docs:
	mkdocs build

serve-docs:
	mkdocs serve

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v


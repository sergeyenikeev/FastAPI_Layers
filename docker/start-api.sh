#!/bin/sh
set -eu

python scripts/create_topics.py || true
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8080


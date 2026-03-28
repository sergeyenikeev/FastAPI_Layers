#!/bin/sh
set -eu

python scripts/create_topics.py || true
python -m app.worker


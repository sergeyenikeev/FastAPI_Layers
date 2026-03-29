#!/bin/sh
set -eu

TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Создан локальный .env из .env.example"
fi

if grep -q '^KAFKA_BOOTSTRAP_SERVERS=' .env && ! grep -q '^KAFKA_BOOTSTRAP_SERVERS=\[' .env; then
  python - <<'PY'
from pathlib import Path

path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
updated = []
for line in lines:
    if line.startswith("KAFKA_BOOTSTRAP_SERVERS=") and not line.startswith('KAFKA_BOOTSTRAP_SERVERS=['):
        updated.append('KAFKA_BOOTSTRAP_SERVERS=["kafka:9092"]')
    elif line.startswith("API_KEYS=") and not line.startswith('API_KEYS=['):
        updated.append('API_KEYS=["replace-with-api-key"]')
    else:
        updated.append(line)
path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
fi

docker compose up -d --build

echo "Ожидание готовности API..."
elapsed=0
until curl -fsS "http://localhost:8080/api/v1/health/ready" >/dev/null 2>&1; do
  sleep 3
  elapsed=$((elapsed + 3))
  if [ "$elapsed" -ge "$TIMEOUT_SECONDS" ]; then
    echo "Таймаут ожидания API"
    exit 1
  fi
done

docker compose ps
echo "Локальный стек поднят."

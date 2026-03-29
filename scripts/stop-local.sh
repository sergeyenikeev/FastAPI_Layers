#!/bin/sh
set -eu

if [ "${1:-}" = "--volumes" ]; then
  docker compose down -v
else
  docker compose down
fi

echo "Локальный стек остановлен."

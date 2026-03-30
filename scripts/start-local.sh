#!/bin/sh
set -eu

# Unix-wrapper намеренно минимален: он не дублирует шаги bootstrap, а просто
# делегирует их Python-скрипту, который одинаково работает в CI и локально.
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"

set -- run python scripts/dev_stack.py start --timeout-sec "$TIMEOUT_SECONDS" "$@"
uv "$@"

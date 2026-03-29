#!/bin/sh
set -eu

TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-240}"

set -- run python scripts/dev_stack.py start --timeout-sec "$TIMEOUT_SECONDS" "$@"
uv "$@"

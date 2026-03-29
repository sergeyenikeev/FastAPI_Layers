#!/bin/sh
set -eu

uv run python scripts/dev_stack.py stop "$@"

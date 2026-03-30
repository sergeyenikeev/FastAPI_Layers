#!/bin/sh
set -eu

# Единый stop entrypoint нужен для симметрии с PowerShell-оберткой и для того,
# чтобы документация могла ссылаться на одну и ту же операцию в обеих средах.
uv run python scripts/dev_stack.py stop "$@"

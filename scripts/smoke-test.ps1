param(
    [int]$TimeoutSec = 30
)

# Smoke wrapper запускает публичный сценарий проверки через тот же dev_stack.py,
# чтобы ручная эксплуатация и автоматизированная проверка использовали один код.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

uv run python scripts/dev_stack.py smoke --timeout-sec $TimeoutSec
if ($LASTEXITCODE -ne 0) {
    throw "uv run scripts/dev_stack.py smoke завершился с кодом $LASTEXITCODE"
}

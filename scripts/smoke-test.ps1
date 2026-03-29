param(
    [int]$TimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

uv run python scripts/dev_stack.py smoke --timeout-sec $TimeoutSec
if ($LASTEXITCODE -ne 0) {
    throw "uv run scripts/dev_stack.py smoke завершился с кодом $LASTEXITCODE"
}

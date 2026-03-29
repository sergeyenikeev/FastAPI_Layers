param(
    [switch]$Volumes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptArgs = @("run", "python", "scripts/dev_stack.py", "stop")
if ($Volumes) {
    $scriptArgs += "--volumes"
}

uv @scriptArgs
if ($LASTEXITCODE -ne 0) {
    throw "uv run scripts/dev_stack.py stop завершился с кодом $LASTEXITCODE"
}

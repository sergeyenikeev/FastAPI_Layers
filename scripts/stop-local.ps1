param(
    [switch]$Volumes
)

# Отдельный stop-wrapper нужен, чтобы путь "поднять/остановить" выглядел
# одинаково для команды, даже если под капотом все делается через uv + Python.
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

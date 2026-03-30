param(
    [switch]$NoBuild,
    [switch]$SkipSmoke,
    [int]$TimeoutSec = 240
)

# PowerShell wrapper оставляет Windows-разработчику короткую команду запуска,
# но вся настоящая логика живет в одном Python-скрипте dev_stack.py, чтобы
# orchestration локального стека не дублировалась между shell-окружениями.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptArgs = @("run", "python", "scripts/dev_stack.py", "start", "--timeout-sec", "$TimeoutSec")
if ($NoBuild) {
    $scriptArgs += "--no-build"
}
if ($SkipSmoke) {
    $scriptArgs += "--skip-smoke"
}

uv @scriptArgs
if ($LASTEXITCODE -ne 0) {
    throw "uv run scripts/dev_stack.py start завершился с кодом $LASTEXITCODE"
}

param(
    [switch]$Volumes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$composeArgs = @("compose", "down")
if ($Volumes) {
    $composeArgs += "-v"
}

docker @composeArgs
Write-Host "Локальный стек остановлен."

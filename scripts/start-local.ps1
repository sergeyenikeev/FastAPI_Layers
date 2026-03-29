param(
    [switch]$NoBuild,
    [switch]$SkipSmoke,
    [int]$TimeoutSec = 240
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-EnvFile {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Создан локальный .env из .env.example"
        return
    }

    $content = Get-Content ".env"
    $normalized = $content | ForEach-Object {
        if ($_ -match "^KAFKA_BOOTSTRAP_SERVERS=" -and $_ -notmatch "^\w+=\[") {
            return 'KAFKA_BOOTSTRAP_SERVERS=["kafka:9092"]'
        }
        if ($_ -match "^API_KEYS=" -and $_ -notmatch "^\w+=\[") {
            return 'API_KEYS=["replace-with-api-key"]'
        }
        return $_
    }
    Set-Content ".env" $normalized
}

function Wait-ForUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSec
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Seconds 3
            continue
        }
        Start-Sleep -Seconds 3
    }

    throw "Таймаут ожидания доступности URL: $Url"
}

Ensure-EnvFile

$composeArgs = @("compose", "up", "-d")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

Write-Host "Запуск docker compose..."
docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up завершился с кодом $LASTEXITCODE"
}

Write-Host "Ожидание готовности API..."
Wait-ForUrl -Url "http://localhost:8080/api/v1/health/ready" -TimeoutSec $TimeoutSec

Write-Host "Текущее состояние контейнеров:"
docker compose ps

if (-not $SkipSmoke) {
    Write-Host "Запуск smoke-проверки..."
    & "$PSScriptRoot\smoke-test.ps1"
}

Write-Host "Локальный стек поднят."

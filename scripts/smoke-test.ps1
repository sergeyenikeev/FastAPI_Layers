param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FirstValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RawValue
    )

    $trimmed = $RawValue.Trim()
    if ($trimmed.StartsWith("[")) {
        $parsed = $trimmed | ConvertFrom-Json
        if ($parsed -is [System.Array]) {
            return [string]$parsed[0]
        }
        return [string]$parsed
    }

    return [string](($trimmed -split ",")[0].Trim())
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path ".env")) {
        throw "Файл .env не найден"
    }

    $line = Get-Content ".env" | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    return ($line -split "=", 2)[1]
}

function Wait-ForExecutionProjection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecutionId,
        [Parameter(Mandatory = $true)]
        [hashtable]$Headers,
        [int]$TimeoutSec = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod `
                -Uri "http://localhost:8080/api/v1/executions/$ExecutionId" `
                -Headers $Headers `
                -Method Get
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Проекция execution не появилась за ${TimeoutSec}с: $ExecutionId"
}

$apiKey = Get-EnvValue -Name "API_KEYS"
if (-not $apiKey) {
    throw "В .env не найден API_KEYS"
}
$apiKey = Get-FirstValue -RawValue $apiKey

$headers = @{
    "X-API-Key" = $apiKey
}

Write-Host "Проверка /api/v1/health/live"
$live = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/health/live" -Headers $headers -Method Get

Write-Host "Проверка /api/v1/health/ready"
$ready = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/health/ready" -Headers $headers -Method Get

Write-Host "Проверка /docs"
$docs = Invoke-WebRequest -Uri "http://localhost:8080/docs" -UseBasicParsing -TimeoutSec 10
if ($docs.StatusCode -ne 200) {
    throw "Swagger UI недоступен"
}

Write-Host "Запуск тестового сценария"
$payload = Get-Content "examples/workflow_execution_with_validator.json" | ConvertFrom-Json
$execution = Invoke-RestMethod `
    -Uri "http://localhost:8080/api/v1/executions" `
    -Headers $headers `
    -Method Post `
    -ContentType "application/json" `
    -Body ($payload | ConvertTo-Json -Depth 10)

Start-Sleep -Seconds 2
$executionState = Wait-ForExecutionProjection -ExecutionId $execution.entity_id -Headers $headers

[pscustomobject]@{
    LiveStatus = $live.status
    ReadyStatus = $ready.status
    ExecutionId = $execution.entity_id
    ExecutionStatus = $executionState.status
    StepNames = ($executionState.steps.step_name -join ", ")
} | Format-List

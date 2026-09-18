param([switch]$WithoutBlockchain, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$backendArgs = @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', "$Port")
if ($WithoutBlockchain) {
    $env:BLOCKCHAIN_ENABLED = 'false'
    Write-Host 'Blockchain: intentionally disabled; screening remains available.'
} else {
    if (-not (Test-Path -LiteralPath 'backend/.env.audit-local')) {
        throw 'Run scripts/deploy-local.ps1 first, or use -WithoutBlockchain.'
    }
    # Uvicorn preserves process variables; reject stale overrides instead of silently using them.
    $overrides = Get-ChildItem Env:BLOCKCHAIN_* | Select-Object -ExpandProperty Name
    if ($overrides) { throw "Remove process environment overrides before loading local config: $($overrides -join ', ')" }
    $backendArgs += @('--env-file', 'backend/.env.audit-local')
}
Write-Host "Backend: starting http://127.0.0.1:$Port; database initializes and demo records seed automatically."
& python @backendArgs
exit $LASTEXITCODE

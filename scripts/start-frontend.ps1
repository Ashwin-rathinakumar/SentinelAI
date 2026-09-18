param([int]$Port = 5173, [string]$ApiUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../frontend')
$env:VITE_API_URL = $ApiUrl
Write-Host "Frontend: starting http://127.0.0.1:$Port; backend $ApiUrl."
& npm.cmd run dev -- --host 127.0.0.1 --port $Port --strictPort
exit $LASTEXITCODE

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../blockchain')
Write-Host 'Hardhat: starting http://127.0.0.1:8545 (local development only). Keep this terminal open.'
& npx.cmd hardhat node --hostname 127.0.0.1
exit $LASTEXITCODE

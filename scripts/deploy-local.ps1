$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../blockchain')
Write-Host 'Deploying local audit contract. Hardhat must already be running on port 8545.'
& npx.cmd hardhat run scripts/deploy.js --network localhost
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npx.cmd hardhat run scripts/configure-local.js --network localhost
exit $LASTEXITCODE

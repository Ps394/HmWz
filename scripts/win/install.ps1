$ErrorActionPreference = "Stop"
$scriptDirectory = $PSScriptRoot

Write-Host "=== HmWz installation ===" -ForegroundColor Cyan

& (Join-Path $scriptDirectory "create_venv.ps1")
& (Join-Path $scriptDirectory "install_dependencies.ps1")
& (Join-Path $scriptDirectory "configure_token.ps1")
& (Join-Path $scriptDirectory "install_service.ps1")

Write-Host ""
Write-Host "Installation complete. The configured scheduled task is registered and running." -ForegroundColor Green

# Reserve Juggler: Quick Setup Script
Write-Host "=== INITIALIZING RESERVE JUGGLER ENVIRONMENT ===" -ForegroundColor Cyan

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"

if (-not (Test-Path $envFile)) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Gray
    Copy-Item $envExample $envFile
    Write-Host ".env created." -ForegroundColor Green
} else {
    Write-Host ".env already exists." -ForegroundColor Gray
}

Write-Host "Setup complete. Run .\scripts\run.ps1 -Mode Docker to start." -ForegroundColor Green

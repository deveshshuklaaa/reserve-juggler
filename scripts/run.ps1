# Reserve Juggler: Service Launch Script
param (
    [ValidateSet("Docker", "Local")]
    [string]$Mode = "Docker",
    [switch]$Down = $false
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")

if ($Down) {
    Write-Host "Stopping Reserve Juggler Docker stack..." -ForegroundColor Yellow
    Push-Location $root
    docker compose down
    Pop-Location
    exit 0
}

Write-Host "=== LAUNCHING RESERVE JUGGLER ($Mode Mode) ===" -ForegroundColor Cyan

switch ($Mode) {
    "Docker" {
        Push-Location $root
        Write-Host "Starting all services via Docker Compose..."
        docker compose up -d --build
        Pop-Location
        Write-Host "`nContainers initiated. Run .\scripts\health-check.ps1 to verify endpoints." -ForegroundColor Green
    }
    "Local" {
        Write-Host "To run services natively:" -ForegroundColor Yellow
        Write-Host "1. Database: Ensure PostgreSQL is running on port 5432"
        Write-Host "2. Backend:  cd backend; uvicorn app.main:app --reload --port 8000"
        Write-Host "3. Frontend: cd frontend; npm run dev"
    }
}

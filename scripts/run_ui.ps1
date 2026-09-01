# Start the React chat UI (Phase 4).
# Usage (from anywhere): .\scripts\run_ui.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
Set-Location $Frontend

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host "Starting UI at http://localhost:5173 (Ctrl+C to stop)" -ForegroundColor Cyan
npm run dev

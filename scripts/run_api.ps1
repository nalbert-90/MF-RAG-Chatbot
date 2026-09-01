# Start the FastAPI backend (Phase 4).
# Usage (from anywhere): .\scripts\run_api.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

Write-Host "Starting API at http://127.0.0.1:8000 (Ctrl+C to stop)" -ForegroundColor Cyan
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

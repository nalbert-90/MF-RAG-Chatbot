# Run the Phase 5 demo script (orchestrator paths, no servers required).
# Usage: .\scripts\demo.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

python -m src.api.demo @args

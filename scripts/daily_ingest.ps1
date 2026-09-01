# Full daily ingest pipeline (Phase 6). Used locally and by GitHub Actions.
# Usage:
#   .\scripts\daily_ingest.ps1
#   .\scripts\daily_ingest.ps1 --offline

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

python -m src.ingest.pipeline --strict-fetch @args

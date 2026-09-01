#!/usr/bin/env bash
# Start the FastAPI backend (Phase 4).
# Usage: ./scripts/run_api.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Starting API at http://127.0.0.1:8000 (Ctrl+C to stop)"
exec uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

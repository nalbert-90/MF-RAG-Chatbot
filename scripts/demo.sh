#!/usr/bin/env bash
# Run the Phase 5 demo script (orchestrator paths, no servers required).
# Usage: ./scripts/demo.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python -m src.api.demo "$@"

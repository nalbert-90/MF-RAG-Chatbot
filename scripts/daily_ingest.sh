#!/usr/bin/env bash
# Full daily ingest pipeline (Phase 6). Used locally and by GitHub Actions.
# Usage:
#   ./scripts/daily_ingest.sh
#   ./scripts/daily_ingest.sh --strict-fetch

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python -m src.ingest.pipeline --strict-fetch "$@"

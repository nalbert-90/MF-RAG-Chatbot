#!/usr/bin/env bash
# Start the React chat UI (Phase 4).
# Usage: ./scripts/run_ui.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -d node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm install
fi

echo "Starting UI at http://localhost:5173 (Ctrl+C to stop)"
exec npm run dev

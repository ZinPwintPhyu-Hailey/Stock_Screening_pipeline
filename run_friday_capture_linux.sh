#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

source .venv/bin/activate

source "$ROOT_DIR/.venv/bin/activate"

set -a
source "$ROOT_DIR/.env"
set +a

python "$ROOT_DIR/src/run_csp_screen.py" \
  --config "$ROOT_DIR/config/settings.json" \
  --out-dir "$ROOT_DIR/output" >> "$ROOT_DIR/logs/friday_capture.log" 2>&1

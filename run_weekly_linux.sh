#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT_DIR"
mkdir -p logs

source "$ROOT_DIR/.venv/bin/activate"

set -a
source "$ROOT_DIR/.env"
set +a

python "$ROOT_DIR/src/run_and_email.py" \
  --config "$ROOT_DIR/config/settings.json" \
  --out-dir "$ROOT_DIR/output" >> "$ROOT_DIR/logs/monday_email.log" 2>&1

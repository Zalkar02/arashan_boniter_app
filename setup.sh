#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_DIR/.venv"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN"
  exit 1
fi

cd "$PROJECT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt
"$VENV_DIR/bin/python" migrate_local_db.py

if [[ -f "$PROJECT_DIR/.app_state/print_settings.example.json" && ! -f "$PROJECT_DIR/.app_state/print_settings.json" ]]; then
  cp "$PROJECT_DIR/.app_state/print_settings.example.json" "$PROJECT_DIR/.app_state/print_settings.json"
fi
if [[ -f "$PROJECT_DIR/sheep_local.example.db" && ! -f "$PROJECT_DIR/sheep_local.db" ]]; then
  cp "$PROJECT_DIR/sheep_local.example.db" "$PROJECT_DIR/sheep_local.db"
fi
if [[ -f "$PROJECT_DIR/last_sync.example.txt" && ! -f "$PROJECT_DIR/last_sync.txt" ]]; then
  cp "$PROJECT_DIR/last_sync.example.txt" "$PROJECT_DIR/last_sync.txt"
fi

echo
echo "Setup complete."
echo "Run the app with: bash run.sh"

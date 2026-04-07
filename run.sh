#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON=""

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [[ -x "$PROJECT_DIR/env/bin/python" ]]; then
  VENV_PYTHON="$PROJECT_DIR/env/bin/python"
fi

if [[ -z "$VENV_PYTHON" ]]; then
  echo "Virtual environment not found."
  echo "Run: bash setup.sh or create env/"
  exit 1
fi

cd "$PROJECT_DIR"
exec "$VENV_PYTHON" app.py

#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
  bash "$PROJECT_DIR/setup.sh"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install pyinstaller

cd "$PROJECT_DIR"
rm -rf build dist
"$VENV_DIR/bin/pyinstaller" --noconfirm arashan_boniter.spec

echo
echo "Build complete:"
echo "  $PROJECT_DIR/dist/ArashanBoniter/ArashanBoniter"

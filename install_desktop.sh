#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Arashan Boniter"
DESKTOP_FILENAME="arashan-boniter.desktop"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
RUN_SCRIPT="$PROJECT_DIR/run.sh"
ICON_PATH="$PROJECT_DIR/assets/app_icon.svg"

mkdir -p "$APPLICATIONS_DIR"

if [[ ! -x "$RUN_SCRIPT" ]]; then
  chmod +x "$RUN_SCRIPT"
fi

DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Система бонитировки
Exec=$RUN_SCRIPT
Path=$PROJECT_DIR
Terminal=false
Categories=Office;"

if [[ -f "$ICON_PATH" ]]; then
  DESKTOP_CONTENT="$DESKTOP_CONTENT
Icon=$ICON_PATH"
fi

printf '%s\n' "$DESKTOP_CONTENT" > "$APPLICATIONS_DIR/$DESKTOP_FILENAME"
chmod +x "$APPLICATIONS_DIR/$DESKTOP_FILENAME"

if [[ -d "$DESKTOP_DIR" ]]; then
  printf '%s\n' "$DESKTOP_CONTENT" > "$DESKTOP_DIR/$DESKTOP_FILENAME"
  chmod +x "$DESKTOP_DIR/$DESKTOP_FILENAME"
fi

echo "Desktop entry installed:"
echo "  $APPLICATIONS_DIR/$DESKTOP_FILENAME"
if [[ -d "$DESKTOP_DIR" ]]; then
  echo "  $DESKTOP_DIR/$DESKTOP_FILENAME"
fi

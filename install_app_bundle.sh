#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$PROJECT_DIR/dist/ArashanBoniter"
APP_NAME="Arashan Boniter"
APP_ID="arashan-boniter"
INSTALL_DIR="$HOME/.local/opt/$APP_ID"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
ICON_PATH="$INSTALL_DIR/assets/app_icon.svg"
EXEC_PATH="$INSTALL_DIR/ArashanBoniter"
DESKTOP_FILENAME="$APP_ID.desktop"

if [[ ! -x "$EXEC_PATH" && ! -x "$BUNDLE_DIR/ArashanBoniter" ]]; then
  echo "Bundle not found."
  echo "Run: bash build_app.sh"
  exit 1
fi

mkdir -p "$HOME/.local/opt" "$APPLICATIONS_DIR"
rm -rf "$INSTALL_DIR"
cp -R "$BUNDLE_DIR" "$INSTALL_DIR"

DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Система бонитировки
Exec=$EXEC_PATH
Path=$INSTALL_DIR
Icon=$ICON_PATH
Terminal=false
Categories=Office;"

printf '%s\n' "$DESKTOP_CONTENT" > "$APPLICATIONS_DIR/$DESKTOP_FILENAME"
chmod +x "$APPLICATIONS_DIR/$DESKTOP_FILENAME"

if [[ -d "$DESKTOP_DIR" ]]; then
  printf '%s\n' "$DESKTOP_CONTENT" > "$DESKTOP_DIR/$DESKTOP_FILENAME"
  chmod +x "$DESKTOP_DIR/$DESKTOP_FILENAME"
fi

echo "Application bundle installed:"
echo "  $INSTALL_DIR"
echo "Desktop entry:"
echo "  $APPLICATIONS_DIR/$DESKTOP_FILENAME"

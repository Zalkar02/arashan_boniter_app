#!/usr/bin/env bash
# Собирает AppImage. Использование: packaging/build_appimage.sh [venv-python]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${1:-$ROOT/.venv/bin/python}"
VERSION="$("$PYTHON_BIN" -c 'from version import __version__; print(__version__)')"
OUT="$ROOT/dist/ArashanBoniter-${VERSION}-x86_64.AppImage"
APPDIR="$ROOT/build/AppDir"
TOOL="$ROOT/build/appimagetool"

cd "$ROOT"
rm -rf build/AppDir dist/ArashanBoniter
"$PYTHON_BIN" -m pip install pyinstaller
"$PYTHON_BIN" -m PyInstaller --noconfirm arashan_boniter.spec

mkdir -p "$APPDIR/usr/lib"
cp -R dist/ArashanBoniter "$APPDIR/usr/lib/ArashanBoniter"
# appimagetool требует PNG в .DirIcon.
cp assets/app_icon.png "$APPDIR/arashan-boniter.png"
cp assets/app_icon.png "$APPDIR/.DirIcon"

cat > "$APPDIR/arashan-boniter.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Arashan Boniter
Comment=Система бонитировки
Exec=ArashanBoniter
Icon=arashan-boniter
Terminal=false
Categories=Office;
DESKTOP

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/ArashanBoniter/ArashanBoniter" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

mkdir -p dist
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "Built: $OUT"

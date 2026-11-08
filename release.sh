#!/usr/bin/env bash
# Использование: ./release.sh 1.3.0 "Что нового"
# Меняет version.py, коммитит, ставит тег v1.3.0 и пушит. Остальное делает GitHub Actions.
set -euo pipefail

VERSION="${1:-}"
NOTES="${2:-}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Использование: ./release.sh X.Y.Z \"описание\"" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Есть незакоммиченные изменения. Сначала закоммитьте их." >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Релиз делается из ветки main." >&2
  exit 1
fi
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
  echo "Тег v$VERSION уже существует." >&2
  exit 1
fi
[[ -n "$NOTES" ]] || NOTES="Версия $VERSION"

printf '"""Единственный источник версии приложения (semver: MAJOR.MINOR.PATCH).\n\nМеняется скриптом release.sh; CI проверяет, что тег релиза совпадает с этим значением.\n"""\n\n__version__ = "%s"\n' "$VERSION" > version.py
git add version.py
git commit -m "release $VERSION"
git tag -a "v$VERSION" -m "$NOTES"
git push origin main "v$VERSION"
echo "Тег v$VERSION отправлен. Сборка: вкладка Actions на GitHub."

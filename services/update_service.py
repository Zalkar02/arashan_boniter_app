"""Проверка и установка обновлений через manifest.json в S3.

Формат манифеста:
{
  "version": "1.3.0",
  "min_supported_version": "1.0.0",
  "notes": "Что нового",
  "platforms": {
    "windows": {"url": "https://.../ArashanBoniter-Setup-1.3.0.exe", "sha256": "...", "size": 123},
    "linux":   {"url": "https://.../ArashanBoniter-1.3.0-x86_64.AppImage", "sha256": "...", "size": 123}
  }
}
"""
import hashlib
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

import requests

from api_config import UPDATE_BASE_URL
from state_paths import APP_STATE_HOME
from version import __version__

MANIFEST_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60
CHUNK_SIZE = 256 * 1024
UPDATES_DIR = os.path.join(APP_STATE_HOME, "updates")


class UpdateError(RuntimeError):
    pass


def platform_key() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def can_self_update() -> bool:
    """Самообновление работает у собранного приложения: .exe на Windows, AppImage на Linux."""
    if not is_frozen():
        return False
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("APPIMAGE"))


def parse_version(value) -> tuple:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    if not match:
        raise UpdateError(f"Некорректная версия: {value!r}")
    return tuple(int(part) for part in match.groups())


def _fetch_manifest(base_url: str) -> dict:
    url = f"{base_url}/manifest.json"
    try:
        response = requests.get(
            url,
            timeout=MANIFEST_TIMEOUT,
            headers={"Cache-Control": "no-cache"},
        )
    except requests.RequestException as exc:
        raise UpdateError(f"Нет связи с сервером обновлений: {exc}") from exc
    if response.status_code != 200:
        raise UpdateError(f"Сервер обновлений ответил {response.status_code}.")
    try:
        manifest = response.json()
    except ValueError as exc:
        raise UpdateError("Сервер обновлений вернул некорректный манифест.") from exc
    if not isinstance(manifest, dict) or "version" not in manifest:
        raise UpdateError("В манифесте обновлений нет версии.")
    return manifest


def check_for_updates(current_version: str = None, base_url: str = None) -> dict:
    current_version = current_version or __version__
    base_url = (UPDATE_BASE_URL if base_url is None else base_url).rstrip("/")
    if not base_url:
        raise UpdateError("Адрес сервера обновлений не настроен (UPDATE_BASE_URL).")

    manifest = _fetch_manifest(base_url)
    current = parse_version(current_version)
    latest = parse_version(manifest["version"])
    min_supported = parse_version(manifest.get("min_supported_version") or "0.0.0")

    asset = (manifest.get("platforms") or {}).get(platform_key())
    has_updates = latest > current
    if has_updates and not asset:
        raise UpdateError("Для вашей системы нет файла обновления.")
    if asset and not (asset.get("url") and asset.get("sha256")):
        raise UpdateError("В манифесте не хватает ссылки или контрольной суммы.")

    return {
        "current_version": current_version,
        "latest_version": str(manifest["version"]),
        "has_updates": has_updates,
        "required": current < min_supported,
        "min_supported_version": str(manifest.get("min_supported_version") or ""),
        "notes": str(manifest.get("notes") or ""),
        "asset": asset,
    }


def download_update(info: dict, progress=None, dest_dir: str = None) -> str:
    """Скачивает файл обновления, проверяет sha256, возвращает путь. progress(done, total)."""
    asset = info.get("asset")
    if not asset:
        raise UpdateError("Нет файла для скачивания.")
    dest_dir = dest_dir or UPDATES_DIR
    os.makedirs(dest_dir, exist_ok=True)

    filename = os.path.basename(urlsplit(asset["url"]).path) or f"update-{info['latest_version']}"
    final_path = os.path.join(dest_dir, filename)
    part_path = final_path + ".part"
    expected = str(asset["sha256"]).lower()
    digest = hashlib.sha256()

    try:
        with requests.get(asset["url"], stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            if response.status_code != 200:
                raise UpdateError(f"Не удалось скачать обновление: {response.status_code}.")
            total = int(response.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            with open(part_path, "wb") as fh:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as exc:
        _remove_quietly(part_path)
        raise UpdateError(f"Ошибка загрузки обновления: {exc}") from exc

    if digest.hexdigest() != expected:
        _remove_quietly(part_path)
        raise UpdateError("Контрольная сумма файла не совпала. Попробуйте ещё раз.")
    os.replace(part_path, final_path)
    return final_path


def _remove_quietly(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


def _clean_child_env() -> dict:
    """Окружение для запуска новой копии из PyInstaller-приложения."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("_PYI_") or key == "_MEIPASS2":
            del env[key]
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = original
    return env


def apply_update(path: str):
    """Запускает установку. После вызова приложение должно завершиться."""
    if not can_self_update():
        raise UpdateError("Автообновление работает только в установленной версии приложения.")

    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
            creationflags=flags,
            close_fds=True,
        )
        return

    target = os.environ["APPIMAGE"]
    staging = os.path.join(os.path.dirname(target), "." + os.path.basename(target) + ".new")
    try:
        with open(path, "rb") as src, open(staging, "wb") as dst:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
        os.chmod(staging, 0o755)
        os.replace(staging, target)
    except OSError as exc:
        _remove_quietly(staging)
        raise UpdateError(f"Не удалось заменить файл приложения {target}: {exc}") from exc
    _remove_quietly(path)
    # Небольшая пауза, чтобы старый процесс успел завершиться.
    subprocess.Popen(
        ["sh", "-c", 'sleep 1; exec "$0"', target],
        env=_clean_child_env(),
        start_new_session=True,
        close_fds=True,
    )

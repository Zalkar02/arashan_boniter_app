"""Переход со старой установки (git-клон + Python) на установленное приложение.

Старые пользователи обновляются кнопкой с `git pull`, поэтому получают этот код как
исходники. Он предлагает один раз перейти на установщик/AppImage из манифеста:
скачивает файл, копирует данные из папки репозитория в папку данных установленного
приложения, устанавливает его и оставляет метку, чтобы старые ярлыки открывали новую версию.
Папка репозитория не удаляется и остаётся резервной копией.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from services.update_service import UpdateError, check_for_updates, download_update, is_frozen
from state_paths import PROJECT_ROOT, installed_state_home

MARKER_PATH = os.path.join(PROJECT_ROOT, ".migrated_to_installed.json")
DB_NAME = "sheep_local.db"
STATE_DIR_NAME = ".app_state"
STATE_FILES = ("last_sync.txt", "sync_conflicts.jsonl")
APP_ID = "arashan-boniter"


def is_legacy_checkout() -> bool:
    """Запуск из git-клона у пользователя. Разработчик отключает переход через ARASHAN_DEV=1."""
    if is_frozen() or os.environ.get("ARASHAN_DEV"):
        return False
    return os.path.isdir(os.path.join(PROJECT_ROOT, ".git"))


def linux_appimage_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Applications", "ArashanBoniter.AppImage")


def windows_exe_path() -> str:
    # Inno Setup без прав администратора ставит в {autopf} = %LOCALAPPDATA%\Programs.
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Programs", "ArashanBoniter", "ArashanBoniter.exe")


def installed_app_path() -> str:
    return windows_exe_path() if sys.platform == "win32" else linux_appimage_path()


def check() -> dict:
    """Данные для окна перехода: последняя версия из манифеста, независимо от версии исходников."""
    info = check_for_updates(current_version="0.0.0")
    if not info.get("asset"):
        raise UpdateError("Для вашей системы нет файла установки.")
    info["legacy"] = True
    info["required"] = False
    return info


def copy_user_data(src_dir: str = PROJECT_ROOT, dest_dir: str = None) -> bool:
    """Копирует базу и состояние. Если у установленного приложения уже есть база, ничего не трогает."""
    dest_dir = dest_dir or installed_state_home()
    src_db = os.path.join(src_dir, DB_NAME)
    dest_db = os.path.join(dest_dir, DB_NAME)
    if os.path.exists(dest_db):
        return False
    os.makedirs(dest_dir, exist_ok=True)

    if os.path.isfile(src_db):
        # backup API даёт целостную копию, даже если база открыта и есть WAL.
        tmp_db = dest_db + ".part"
        src = sqlite3.connect(src_db)
        try:
            dst = sqlite3.connect(tmp_db)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        os.replace(tmp_db, dest_db)

    src_state = os.path.join(src_dir, STATE_DIR_NAME)
    if os.path.isdir(src_state):
        shutil.copytree(src_state, os.path.join(dest_dir, STATE_DIR_NAME), dirs_exist_ok=True)
    for name in STATE_FILES:
        path = os.path.join(src_dir, name)
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(dest_dir, name))
    return True


def _desktop_dir() -> str:
    try:
        result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False)
        path = (result.stdout or "").strip()
        if path and os.path.isdir(path):
            return path
    except OSError:
        pass
    path = os.path.join(os.path.expanduser("~"), "Desktop")
    return path if os.path.isdir(path) else ""


def _linux_desktop_entry(appimage: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Arashan Boniter\n"
        "Comment=Система бонитировки\n"
        f'Exec="{appimage}"\n'
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Office;\n"
    )


def replace_linux_shortcuts(appimage: str):
    """Старые ярлыки запускали run.sh; переписываем их на AppImage."""
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    targets = [os.path.join(data_home, "applications", f"{APP_ID}.desktop")]
    desktop = _desktop_dir()
    if desktop:
        targets.append(os.path.join(desktop, f"{APP_ID}.desktop"))
    content = _linux_desktop_entry(appimage)
    for path in targets:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(path, 0o755)
            # Mint/Nemo запускает ярлык с рабочего стола без вопросов только с этой меткой.
            subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True, check=False)
        except OSError:
            pass


def _write_marker(app_path: str, version: str):
    with open(MARKER_PATH, "w", encoding="utf-8") as fh:
        json.dump({"app_path": app_path, "version": version}, fh, ensure_ascii=False)


def migrate(info: dict, progress=None):
    """Скачивает, переносит данные, устанавливает и запускает новое приложение.
    После вызова старое приложение должно завершиться."""
    download_dir = tempfile.mkdtemp(prefix="arashan-migrate-")
    path = download_update(info, progress=progress, dest_dir=download_dir)
    copy_user_data()

    if sys.platform == "win32":
        _write_marker(windows_exe_path(), info["latest_version"])
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        # Установщик сам создаёт ярлык «Arashan Boniter» поверх старого и запускает приложение.
        subprocess.Popen(
            [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            creationflags=flags,
            close_fds=True,
        )
        return

    target = linux_appimage_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        shutil.move(path, target + ".part")
        os.chmod(target + ".part", 0o755)
        os.replace(target + ".part", target)
    except OSError as exc:
        raise UpdateError(f"Не удалось сохранить приложение в {target}: {exc}") from exc
    finally:
        shutil.rmtree(download_dir, ignore_errors=True)
    replace_linux_shortcuts(target)
    _write_marker(target, info["latest_version"])
    _launch(target)


def _launch(app_path: str):
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([app_path], creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([app_path], start_new_session=True, close_fds=True)


def redirect_to_installed() -> bool:
    """Старый ярлык после перехода: запускаем установленное приложение. True — старое должно выйти."""
    if not is_legacy_checkout() or not os.path.isfile(MARKER_PATH):
        return False
    try:
        with open(MARKER_PATH, encoding="utf-8") as fh:
            app_path = json.load(fh).get("app_path") or ""
    except (OSError, ValueError):
        return False
    if not os.path.isfile(app_path):
        return False
    try:
        _launch(app_path)
    except OSError:
        return False
    return True

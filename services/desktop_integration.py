"""Ярлык в меню приложений для AppImage на Linux (создаётся при запуске)."""
import os
import shutil
import sys

from resource_paths import resource_path

APP_ID = "arashan-boniter"
APP_NAME = "Arashan Boniter"


def ensure_linux_desktop_entry():
    appimage = os.environ.get("APPIMAGE")
    if not sys.platform.startswith("linux") or not appimage:
        return

    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    apps_dir = os.path.join(data_home, "applications")
    icon_dir = os.path.join(data_home, "icons", "hicolor", "scalable", "apps")
    desktop_path = os.path.join(apps_dir, f"{APP_ID}.desktop")
    icon_target = os.path.join(icon_dir, f"{APP_ID}.svg")

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Система бонитировки\n"
        f'Exec="{appimage}"\n'
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Office;\n"
    )
    try:
        os.makedirs(apps_dir, exist_ok=True)
        os.makedirs(icon_dir, exist_ok=True)
        icon_source = resource_path("assets", "app_icon.svg")
        if icon_source and os.path.isfile(icon_source):
            shutil.copyfile(icon_source, icon_target)
        existing = None
        if os.path.isfile(desktop_path):
            with open(desktop_path, encoding="utf-8") as fh:
                existing = fh.read()
        if existing != content:
            with open(desktop_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(desktop_path, 0o755)
    except OSError:
        pass

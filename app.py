import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from auth_state import AuthState
from api_config import build_api_url
from main_menu import MainMenu
from resource_paths import resource_path
from services import legacy_migration
from services.auth_service import load_user, restore_authenticated_session
from services.db_service import get_db
from services.desktop_integration import ensure_linux_desktop_entry
from services.guest_records_service import claim_guest_records
from services.single_instance import acquire_instance_lock
from services.sync_controller import SyncController
from update_ui import UpdateController


def main():
    # Старый ярлык после перехода на установленное приложение: открываем его.
    if legacy_migration.redirect_to_installed():
        return
    app = QApplication(sys.argv)
    icon_file = "app_icon.ico" if sys.platform.startswith("win") else "app_icon.svg"
    icon_path = resource_path("assets", icon_file)
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        QMessageBox.information(
            None,
            "Арашан",
            "Приложение уже открыто.\n"
            "Найдите его окно на панели задач (оно может быть свёрнуто).",
        )
        return
    token_refresh_url = build_api_url("/api/token/refresh/")
    me_url = build_api_url("/api/users/me/")
    w = None
    session = get_db()
    claimed = {"sheep_count": 0, "application_count": 0}

    # если есть сохранённый user — используем его сразу
    saved_user = load_user()
    AuthState.user = saved_user

    if saved_user:
        try:
            restored = restore_authenticated_session(token_refresh_url, me_url)
            if restored:
                claimed = claim_guest_records(session)
                w = MainMenu()
        except Exception:
            w = None

    if w is None:
        w = MainMenu()
    sync_controller = SyncController.instance()
    w.show()
    ensure_linux_desktop_entry()
    # фоновая синхронизация: вскоре после запуска и дальше по таймеру
    sync_controller.start_auto()
    w.update_controller = UpdateController(w)
    QTimer.singleShot(2000, lambda: w.update_controller.check(silent=True))
    if claimed["sheep_count"] or claimed["application_count"]:
        w.statusBar().showMessage(
            f"Подтверждено локальных записей: овцы {claimed['sheep_count']}, бонитировки {claimed['application_count']}",
            8000,
        )
    code = app.exec_()
    instance_lock.unlock()
    sys.exit(code)


if __name__ == "__main__":
    main()

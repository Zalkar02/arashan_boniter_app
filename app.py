import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from auth_state import AuthState
from api_config import build_api_url
from main_menu import MainMenu
from resource_paths import resource_path
from services.auth_service import load_user, restore_authenticated_session
from services.db_service import get_db
from services.guest_records_service import claim_guest_records


def main():
    app = QApplication(sys.argv)
    icon_path = resource_path("assets", "app_icon.svg")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
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
    w.show()
    if claimed["sheep_count"] or claimed["application_count"]:
        w.statusBar().showMessage(
            f"Подтверждено локальных записей: овцы {claimed['sheep_count']}, бонитировки {claimed['application_count']}",
            8000,
        )
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

import sys, json, os, requests
from PyQt5.QtWidgets import QApplication
from login import LoginWindow
from auth_state import AuthState
from main_menu import MainMenu


def main():
    app = QApplication(sys.argv)
    TOKEN_FILE = "tokens.json"
    USER_FILE = "user.json"
    TOKEN_REFRESH_URL = "https://arashan.zet.kg/api/token/refresh/"
    ME_URL = "https://arashan.zet.kg/api/users/me/"
    w = None

    # если есть сохранённый user — используем его сразу
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, "r", encoding="utf-8") as f:
                AuthState.user = json.load(f)
        except Exception:
            AuthState.user = None

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            refresh = data.get("refresh")
            if refresh:
                r = requests.post(TOKEN_REFRESH_URL, json={"refresh": refresh}, timeout=10)
                if r.status_code == 200:
                    access = r.json().get("access")
                    if access:
                        AuthState.access = access
                        AuthState.refresh = refresh
                        try:
                            me = requests.get(ME_URL, headers={"Authorization": f"Bearer {access}"}, timeout=10)
                            if me.status_code == 200:
                                AuthState.user = me.json()
                                with open(USER_FILE, "w", encoding="utf-8") as f:
                                    json.dump(AuthState.user, f, ensure_ascii=False)
                        except Exception:
                            pass
                        w = MainMenu()
        except Exception:
            w = None

    if w is None:
        if AuthState.user is not None:
            w = MainMenu()
        else:
            w = LoginWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

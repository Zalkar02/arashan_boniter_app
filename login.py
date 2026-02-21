# login.py — окно входа
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence
import json, os, requests

from auth_state import AuthState
from main_menu import MainMenu

try:
    from db.models import init_db, User
    db = init_db()
except Exception as e:
    db = None
    User = None
    _db_error = str(e)
else:
    _db_error = None


class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Вход")
        self.resize(520, 360)

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        root = QWidget(self)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(32, 32, 32, 32)
        v.setSpacing(16)

        title = QLabel("Вход в систему")
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 4)
        tf.setBold(True)
        title.setFont(tf)
        title.setAlignment(Qt.AlignHCenter)
        v.addWidget(title)

        form = QFormLayout()
        self.ed_username = QLineEdit()
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.Password)
        form.addRow("Логин", self.ed_username)
        form.addRow("Пароль", self.ed_password)
        v.addLayout(form)

        self.btn_login = QPushButton("Войти")
        self.btn_login.setShortcut(QKeySequence("Return"))
        v.addWidget(self.btn_login)

        self.btn_login.clicked.connect(self._login)

    def _login(self):
        TOKEN_URL = "https://arashan.zet.kg/api/token/"
        ME_URL = "https://arashan.zet.kg/api/users/me/"
        TOKEN_FILE = "tokens.json"
        USER_FILE = "user.json"
        username = self.ed_username.text().strip()
        password = self.ed_password.text()
        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Введите логин и пароль")
            return
        try:
            r = requests.post(TOKEN_URL, json={"username": username, "password": password}, timeout=10)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Сервер недоступен: {e}")
            return
        if r.status_code != 200:
            QMessageBox.warning(self, "Ошибка", "Неверный логин или пароль")
            return
        data = r.json()
        access = data.get("access")
        refresh = data.get("refresh")
        if not access or not refresh:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить токены")
            return
        AuthState.access = access
        AuthState.refresh = refresh
        # загрузить профиль пользователя
        try:
            me = requests.get(ME_URL, headers={"Authorization": f"Bearer {access}"}, timeout=10)
            if me.status_code == 200:
                AuthState.user = me.json()
                with open(USER_FILE, "w", encoding="utf-8") as f:
                    json.dump(AuthState.user, f, ensure_ascii=False)
        except Exception:
            pass
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"access": access, "refresh": refresh}, f)

        self.next = MainMenu()
        self.next.show()
        self.close()

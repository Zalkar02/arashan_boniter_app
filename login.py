# login.py — окно входа
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence

from api_config import build_api_url
from main_menu import MainMenu
from services.auth_service import login_user
from services.db_service import get_db
from services.guest_records_service import claim_guest_records

try:
    from db.models import User
    db = get_db()
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
        token_url = build_api_url("/api/token/")
        me_url = build_api_url("/api/users/me/")
        username = self.ed_username.text().strip()
        password = self.ed_password.text()
        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Введите логин и пароль")
            return
        try:
            login_user(token_url, me_url, username, password)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            return

        claimed = {"sheep_count": 0, "application_count": 0}
        if db is not None:
            try:
                claimed = claim_guest_records(db)
            except Exception:
                db.rollback()

        self.next = MainMenu()
        self.next.show()
        if claimed["sheep_count"] or claimed["application_count"]:
            self.next.statusBar().showMessage(
                f"Подтверждено локальных записей: овцы {claimed['sheep_count']}, бонитировки {claimed['application_count']}",
                8000,
            )
        self.close()

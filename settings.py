# settings.py — настройки и смена пользователя
import json, os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence

from auth_state import AuthState


TOKEN_FILE = "tokens.json"
USER_FILE = "user.json"


class SettingsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(800, 600)

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        root = QWidget(self)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title = QLabel("Настройки")
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 4)
        tf.setBold(True)
        title.setFont(tf)
        v.addWidget(title)

        user_name = ""
        if AuthState.user:
            user_name = AuthState.user.get("name") or AuthState.user.get("username") or ""
        self.lbl_user = QLabel(f"Текущий пользователь: {user_name or '—'}")
        v.addWidget(self.lbl_user)

        row = QHBoxLayout()
        self.btn_logout = QPushButton("Сменить пользователя")
        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        row.addWidget(self.btn_logout)
        row.addStretch(1)
        row.addWidget(self.btn_back)
        v.addLayout(row)

        self.btn_logout.clicked.connect(self._logout)
        self.btn_back.clicked.connect(self.close)

    def _logout(self):
        from login import LoginWindow
        self.next = LoginWindow()
        self.next.show()
        self.close()
        prev = getattr(self, "prev", None)
        prev.close()

    def closeEvent(self, ev):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

# main_menu.py — главное меню без .ui (PyQt5)
import sys, os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QKeySequence

from owner_select import OwnerSelect as OwnerSelectClass
from resource_paths import resource_path
from history import HistoryWindow
from database_browser import DatabaseBrowserWindow
from auth_state import AuthState
from services.user_context_service import get_current_user_name
from settings import SettingsWindow

THEME_PATH = resource_path("styles", "light_theme.qss")
ICON_PATH = resource_path("assets", "app_icon.svg")

class MainMenu(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Арашан — Главное меню")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self.showMaximized() 

        # Белый фон
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        # Тема (если есть)
        if os.path.exists(THEME_PATH):
            with open(THEME_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

        # Контейнер
        root = QWidget(self)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(32, 32, 32, 32)
        v.setSpacing(24)

        # Заголовки
        title = QLabel("Арашан — система бонитировки", self)
        title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        tf = QFont(); tf.setPointSize(24); tf.setBold(True)
        title.setFont(tf)
        v.addWidget(title)

        # subtitle = QLabel("Выберите действие", self)
        # subtitle.setAlignment(Qt.AlignHCenter)
        # v.addWidget(subtitle)

        # Ряд кнопок
        row = QHBoxLayout(); row.setSpacing(16); v.addLayout(row, stretch=1)
        btn_style = (
            "QPushButton{background:#f4f6f8;border:1px solid #e2e5e9;border-radius:12px;"
            "padding:18px 24px;font-size:18px;}"
            "QPushButton:hover{background:#eef1f4;}"
            "QPushButton:pressed{background:#e9ecef;}"
        )

        self.btn_start = QPushButton("Начать бонитировку")
        self.btn_start.setMinimumHeight(96)
        self.btn_start.setStyleSheet(btn_style)
        self.btn_start.setShortcut(QKeySequence("Ctrl+N"))
        self.btn_start.clicked.connect(self.open_owner_select)
        row.addWidget(self.btn_start, 1)

        self.btn_history = QPushButton("История")
        self.btn_history.setMinimumHeight(96)
        self.btn_history.setStyleSheet(btn_style)
        self.btn_history.setShortcut(QKeySequence("Ctrl+H"))
        self.btn_history.clicked.connect(self.view_history)
        row.addWidget(self.btn_history, 1)

        self.btn_database = QPushButton("База данных")
        self.btn_database.setMinimumHeight(96)
        self.btn_database.setStyleSheet(btn_style)
        self.btn_database.setShortcut(QKeySequence("Ctrl+D"))
        self.btn_database.clicked.connect(self.open_database)
        row.addWidget(self.btn_database, 1)

        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.setMinimumHeight(96)
        self.btn_settings.setStyleSheet(btn_style)
        self.btn_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.btn_settings.clicked.connect(self.open_settings)
        row.addWidget(self.btn_settings, 1)

        # Подсказка
        hint = QLabel("Горячие клавиши:  Ctrl+N — Начать,  Ctrl+H — История,  Ctrl+D — База данных,  Ctrl+, — Настройки,  Ctrl+Q — Выход")
        hint.setAlignment(Qt.AlignHCenter)
        v.addWidget(hint)

        user_name = get_current_user_name(AuthState.user)
        self.lbl_user = QLabel(f"Бонитёр: {user_name or '—'}")
        self.lbl_user.setAlignment(Qt.AlignHCenter)
        v.addWidget(self.lbl_user)

        # Ctrl+Q — выход
        quit_btn = QPushButton(self)
        quit_btn.setShortcut(QKeySequence("Ctrl+Q"))
        quit_btn.clicked.connect(self.close)
        quit_btn.setVisible(False)

        self.statusBar().showMessage("Готово")

    def open_owner_select(self):
        if OwnerSelectClass is None:
            QMessageBox.information(self, "Старт", "Окно OwnerSelect не найдено.")
            return
        self.next = OwnerSelectClass()
        self.next.prev = self        # дать ссылку на себя
        self.next.show()
        self.hide()                 

    def view_history(self):
        self.next = HistoryWindow(self)
        self.next.prev = self
        self.next.show()
        self.hide()

    def open_settings(self):
        self.next = SettingsWindow(self)
        self.next.prev = self
        self.next.show()
        self.hide()

    def open_database(self):
        self.next = DatabaseBrowserWindow(self)
        self.next.prev = self
        self.next.show()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    w = MainMenu()
    w.show()
    sys.exit(app.exec_())

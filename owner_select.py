# owner_select.py — выбор владельца (PyQt5), улучшенный поиск и UX
import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence
from unicodedata import normalize
import re
from owner_create import OwnerCreateDialog

SheepCreateWindowClass = None
try:
    from sheep_create import SheepCreateWindow as SheepCreateWindowClass
except Exception:
    SheepCreateWindowClass = None

# ── БД ──────────────────────────────────────────────────────
try:
    from db.models import init_db, User
    db = init_db()
except Exception as e:
    db = None
    User = None
    _db_error = str(e)
else:
    _db_error = None

THEME_PATH = os.path.join("styles", "light_theme.qss")

# Опциональный импорт следующего экрана (если появится)
SheepListClass = None
try:
    from sheep_list import SheepList as SheepListClass
except Exception:
    SheepListClass = None

def _norm(s: str) -> str:
    """Юникод-нормализация + схлопывание пробелов + casefold."""
    if not s:
        return ""
    s = normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _digits(s: str) -> str:
    """Оставить только цифры (для сравнения телефонов)."""
    return "".join(ch for ch in (s or "") if ch.isdigit())


class OwnerSelect(QMainWindow):
    def __init__(self):
        super().__init__()
        self._suppress_restore = False
        self.setWindowTitle("Выбор владельца")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self.showMaximized() 

        # Базовая палитра (светлая)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        # Тема (если есть)
        if os.path.exists(THEME_PATH):
            with open(THEME_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

        # ── Разметка ─────────────────────────────────────────
        root = QWidget(self)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title = QLabel("Найдите владельца по имени или телефону")
        title.setAlignment(Qt.AlignLeft)
        v.addWidget(title)

        top = QHBoxLayout()
        v.addLayout(top)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("ФИО или телефон ")
        # Живой поиск
        self.input_search.textChanged.connect(self.search_owners)
        # Enter = найти
        self.input_search.returnPressed.connect(self.search_owners)

        self.btn_search = QPushButton("Найти")
        self.btn_search.setShortcut(QKeySequence("Return"))
        self.btn_search.clicked.connect(self.search_owners)

        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.setShortcut(QKeySequence("Esc"))
        self.btn_clear.clicked.connect(self.clear_search)

        self.btn_add_owner = QPushButton("Добавить владельца")
        self.btn_add_owner.clicked.connect(self.add_owner)

        top.addWidget(self.input_search, 4)
        top.addWidget(self.btn_search, 1)
        top.addWidget(self.btn_clear, 1)
        top.addWidget(self.btn_add_owner, 2)

        self.list_owners = QListWidget()
        # шрифт списка покрупнее
        self.list_owners.setObjectName("ownersList")              # задаём id
        self.list_owners.setStyleSheet("#ownersList { font-size: 20px; }")
        self.list_owners.setSpacing(4)  # пусть отступы останутся
        self.list_owners.itemDoubleClicked.connect(lambda _: self.continue_with_owner())
        v.addWidget(self.list_owners, 1)

        bottom = QHBoxLayout()
        v.addLayout(bottom)

        self.btn_focus = QPushButton("Фокус на поиск")
        self.btn_focus.setShortcut(QKeySequence("Ctrl+F"))
        self.btn_focus.clicked.connect(lambda: self.input_search.setFocus())

        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Alt+Left"))
        self.btn_back.clicked.connect(self.go_back)

        self.btn_continue = QPushButton("Продолжить")
        self.btn_continue.setShortcut(QKeySequence("Ctrl+Enter"))
        self.btn_continue.clicked.connect(self.continue_with_owner)

        bottom.addWidget(self.btn_back)
        bottom.addWidget(self.btn_focus)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_continue)

        # Проверка БД
        if db is None or User is None:
            QMessageBox.critical(self, "База данных", f"База недоступна.\n{_db_error or ''}")
        else:
            # Первичная загрузка: показать всех
            self.search_owners()

        self.statusBar().showMessage("Готово")

    def closeEvent(self, ev):
        # При переходе на главное меню не открывать его обратно
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

    # ── Логика ──────────────────────────────────────────────

    def _all_users(self):
        if db is None or User is None:
            return []
        try:
            return db.query(User).order_by(User.name).all()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return []

    def _match_user(self, u, q_norm: str, q_digits: str) -> bool:
        """Совпадение по имени/логину (нормализовано) или по телефону (цифры)."""
        name_ok = q_norm in _norm(u.name)
        phone_ok = (q_digits and q_digits in _digits(u.phone))
        return name_ok or phone_ok

    def search_owners(self):
        raw = (self.input_search.text() or "").strip()
        self.list_owners.clear()

        if db is None or User is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
            return

        q_norm = _norm(raw)
        q_digits = _digits(raw)

        # Пустой запрос — показать всех
        candidates = self._all_users()
        if not raw:
            owners = candidates
        else:
            owners = [o for o in candidates if self._match_user(o, q_norm, q_digits)]

        if not owners:
            self.statusBar().showMessage("Совпадений не найдено")
            return

        for o in owners:
            # Формат отображения
            parts = [
                o.name or "Без имени",
                (o.phone or "").strip(),
                (o.city or "").strip(),
                # f"логин: {o.username or '—'}",
            ]
            display = " • ".join([p for p in parts if p])
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, o.id)
            self.list_owners.addItem(item)

        self.statusBar().showMessage(f"Найдено: {len(owners)}")

        # Выделим первую строку для удобства
        if self.list_owners.count() > 0:
            self.list_owners.setCurrentRow(0)

    def clear_search(self):
        self.input_search.clear()
        self.input_search.setFocus()

    def add_owner(self):
        dlg = OwnerCreateDialog(self)
        if dlg.exec_() == dlg.Accepted and dlg.created_id:
            # После создания — перезагрузим список и выделим созданного
            self.search_owners()
            for i in range(self.list_owners.count()):
                it = self.list_owners.item(i)
                if it.data(Qt.UserRole) == dlg.created_id:
                    self.list_owners.setCurrentItem(it)
                    break
            self.statusBar().showMessage("Владелец создан и добавлен в список", 5000)

    def continue_with_owner(self):
        it = self.list_owners.currentItem()
        if not it:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца")
            return

        owner_id = it.data(Qt.UserRole)

        # Открываем немодальное окно создания овцы
        if SheepCreateWindowClass is not None:
            self.next = SheepCreateWindowClass(owner_id, self)
            # показать назад к этому окну после закрытия:
            self.next.prev = self
            # по завершению можно показать всплывашку в статус-баре
            self.next.created.connect(lambda sid: self.statusBar().showMessage(f"Овца создана (ID {sid})", 5000))
            self.next.showMaximized()
            
            self.hide()   # прячем список владельцев на время создания
            return

        QMessageBox.information(self, "Выбор", f"Выбран владелец ID: {owner_id}\n(окно создания овцы не найдено)")

    def go_back(self):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        self.close()

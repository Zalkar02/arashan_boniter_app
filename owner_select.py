# owner_select.py — выбор владельца (PyQt5), улучшенный поиск и UX
import os
from auth_state import AuthState
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence
from PyQt5.QtCore import QSize
from owner_create import OwnerCreateDialog
from resource_paths import resource_path
from services.db_service import get_db
from services.owner_search_service import find_owners, format_owner_display
from services.owner_service import soft_delete_owner

SheepCreateWindowClass = None
try:
    from sheep_create import SheepCreateWindow as SheepCreateWindowClass
except Exception:
    SheepCreateWindowClass = None

# ── БД ──────────────────────────────────────────────────────
try:
    from db.models import User
    db = get_db()
except Exception as e:
    db = None
    User = None
    _db_error = str(e)
else:
    _db_error = None

THEME_PATH = resource_path("styles", "light_theme.qss")

# Опциональный импорт следующего экрана (если появится)
SheepListClass = None
try:
    from sheep_list import SheepList as SheepListClass
except Exception:
    SheepListClass = None


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
        self.btn_edit_owner = QPushButton("Редактировать")
        self.btn_edit_owner.clicked.connect(self.edit_owner)
        self.btn_delete_owner = QPushButton("Удалить")
        self.btn_delete_owner.clicked.connect(self.delete_owner)

        top.addWidget(self.input_search, 4)
        top.addWidget(self.btn_search, 1)
        top.addWidget(self.btn_clear, 1)
        top.addWidget(self.btn_add_owner, 2)
        top.addWidget(self.btn_edit_owner, 1)
        top.addWidget(self.btn_delete_owner, 1)

        self.list_owners = QListWidget()
        # шрифт списка покрупнее
        self.list_owners.setObjectName("ownersList")              # задаём id
        self.list_owners.setStyleSheet(
            """
            #ownersList {
                font-size: 16px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
            }
            #ownersList::item {
                padding: 0px;
                margin: 0px;
            }
            #ownersList::item:selected {
                background: #dbeafe;
            }
            """
        )
        self.list_owners.setSpacing(0)
        self.list_owners.setUniformItemSizes(False)
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

    def search_owners(self):
        raw = (self.input_search.text() or "").strip()
        self.list_owners.clear()

        if db is None or User is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
            return

        try:
            owners = find_owners(db, User, raw)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return

        if not owners:
            self.statusBar().showMessage("Совпадений не найдено")
            return

        for o in owners:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, o.id)
            item.setSizeHint(QSize(0, 98))
            self.list_owners.addItem(item)
            self.list_owners.setItemWidget(item, self._build_owner_item_widget(o))

        self.statusBar().showMessage(f"Найдено: {len(owners)}")

        # Выделим первую строку для удобства
        if self.list_owners.count() > 0:
            self.list_owners.setCurrentRow(0)

    def clear_search(self):
        self.input_search.clear()
        self.input_search.setFocus()

    def _build_owner_item_widget(self, owner):
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 8)
        layout.setSpacing(6)

        lines = format_owner_display(owner).splitlines()
        name_text = lines[0] if lines else (owner.name or "Без имени")
        details_text = lines[1] if len(lines) > 1 else ""
        meta_text = lines[2] if len(lines) > 2 else ""

        lbl_name = QLabel(name_text)
        name_font = lbl_name.font()
        name_font.setBold(True)
        name_font.setPointSize(name_font.pointSize() + 1)
        lbl_name.setFont(name_font)
        lbl_name.setStyleSheet("color: #111827;")
        layout.addWidget(lbl_name)

        lbl_details = QLabel(details_text)
        lbl_details.setWordWrap(True)
        lbl_details.setStyleSheet("color: #374151;")
        layout.addWidget(lbl_details)

        lbl_meta = QLabel(meta_text)
        lbl_meta.setWordWrap(True)
        lbl_meta.setStyleSheet("color: #6b7280;")
        layout.addWidget(lbl_meta)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Plain)
        divider.setStyleSheet("color: #e5e7eb; background: #e5e7eb; max-height: 1px;")
        layout.addWidget(divider)
        return card

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

    def edit_owner(self):
        it = self.list_owners.currentItem()
        if not it:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца")
            return
        owner_id = it.data(Qt.UserRole)
        owner = db.query(User).filter_by(id=owner_id, is_deleted=False).first()
        if owner is None:
            QMessageBox.warning(self, "Ошибка", "Владелец не найден")
            return
        dlg = OwnerCreateDialog(self, owner=owner)
        if dlg.exec_() == dlg.Accepted:
            self.search_owners()
            self.statusBar().showMessage("Владелец обновлён", 5000)

    def delete_owner(self):
        it = self.list_owners.currentItem()
        if not it:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца")
            return
        owner_id = it.data(Qt.UserRole)
        owner = db.query(User).filter_by(id=owner_id, is_deleted=False).first()
        if owner is None:
            QMessageBox.warning(self, "Ошибка", "Владелец не найден")
            return
        current_user_id = (AuthState.user or {}).get("id")
        if current_user_id is None:
            QMessageBox.warning(self, "Удаление", "Для удаления нужно войти в систему.")
            return
        answer = QMessageBox.question(
            self,
            "Удаление владельца",
            f"Удалить владельца «{owner.name or owner.username or owner.id}»?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            soft_delete_owner(db, owner, current_user_id)
        except Exception as e:
            QMessageBox.warning(self, "Удаление", str(e))
            return
        self.search_owners()
        self.statusBar().showMessage("Владелец удалён", 5000)

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

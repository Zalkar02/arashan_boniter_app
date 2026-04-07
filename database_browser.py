from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QKeySequence, QPalette
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from owner_create import OwnerCreateDialog
from sheep_create import SheepCreateWindow
from services.db_service import get_db
from services.database_browser_service import (
    get_owner_regions,
    get_owner_rows,
    get_sheep_rows,
)
from services.owner_search_service import _display_area, _display_region

try:
    from db.models import User, Sheep, Color, Owner
    db = get_db()
except Exception as e:
    db = None
    User = None
    Sheep = None
    Color = None
    Owner = None
    _db_error = str(e)
else:
    _db_error = None

TABLE_STYLE = """
QTableWidget {
    gridline-color: #e6e8eb;
    background: #ffffff;
    alternate-background-color: #f8fafc;
    selection-background-color: #dbeafe;
    selection-color: #111111;
}
QHeaderView::section {
    background: #f3f4f6;
    color: #111111;
    padding: 8px;
    border: 0;
    border-bottom: 1px solid #d1d5db;
    border-right: 1px solid #e5e7eb;
    font-weight: 600;
}
"""


class DatabaseBrowserWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress_restore = False
        self.setWindowTitle("База данных")
        self.resize(1400, 860)
        self.setMinimumSize(1100, 700)
        self.showMaximized()

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("База данных")
        font = title.font()
        font.setPointSize(font.pointSize() + 5)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch(1)

        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        self.btn_back.clicked.connect(self.go_back)
        header.addWidget(self.btn_back)
        layout.addLayout(header)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        self._build_owners_tab()
        self._build_sheep_tab()

        if db is None:
            QMessageBox.critical(self, "База данных", _db_error or "База недоступна")
            return

        self.reload_owners()
        self.reload_sheep()

    def _build_owners_tab(self):
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        filters = QHBoxLayout()
        self.ed_owner_search = QLineEdit()
        self.ed_owner_search.setPlaceholderText("Поиск по ФИО, логину, телефону, адресу")
        self.ed_owner_search.textChanged.connect(self.reload_owners)
        self.cmb_owner_region = QComboBox()
        self.cmb_owner_region.currentIndexChanged.connect(self.reload_owners)
        self.btn_owner_edit = QPushButton("Редактировать владельца")
        self.btn_owner_edit.clicked.connect(self.edit_selected_owner)
        self.btn_owner_refresh = QPushButton("Обновить")
        self.btn_owner_refresh.clicked.connect(self.reload_owners)
        filters.addWidget(QLabel("Поиск:"))
        filters.addWidget(self.ed_owner_search, 1)
        filters.addWidget(QLabel("Область:"))
        filters.addWidget(self.cmb_owner_region)
        filters.addWidget(self.btn_owner_edit)
        filters.addWidget(self.btn_owner_refresh)
        layout.addLayout(filters)

        self.tbl_owners = QTableWidget(0, 8, self)
        self.tbl_owners.setHorizontalHeaderLabels(
            ["ID", "ФИО", "Логин", "Телефон", "Область", "Район", "Населённый пункт", "Овец"]
        )
        self.tbl_owners.setSortingEnabled(True)
        self.tbl_owners.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_owners.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_owners.setAlternatingRowColors(True)
        self.tbl_owners.itemDoubleClicked.connect(lambda _: self.edit_selected_owner())
        self.tbl_owners.setStyleSheet(TABLE_STYLE)
        header = self.tbl_owners.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        layout.addWidget(self.tbl_owners, 1)

        self.tabs.addTab(tab, "Владельцы")

    def _build_sheep_tab(self):
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        filters = QHBoxLayout()
        self.ed_sheep_search = QLineEdit()
        self.ed_sheep_search.setPlaceholderText("Поиск по ID, кличке, владельцу, окрасу")
        self.ed_sheep_search.textChanged.connect(self.reload_sheep)

        self.cmb_gender = QComboBox()
        self.cmb_gender.addItem("Все", "")
        self.cmb_gender.addItem("Бараны", "B")
        self.cmb_gender.addItem("Матки", "O")
        self.cmb_gender.currentIndexChanged.connect(self.reload_sheep)

        self.cmb_paid = QComboBox()
        self.cmb_paid.addItem("Любая оплата", "")
        self.cmb_paid.addItem("Оплаченные", "paid")
        self.cmb_paid.addItem("Не оплаченные", "unpaid")
        self.cmb_paid.currentIndexChanged.connect(self.reload_sheep)

        self.cmb_synced = QComboBox()
        self.cmb_synced.addItem("Любая синхронизация", "")
        self.cmb_synced.addItem("Синхронизированные", "synced")
        self.cmb_synced.addItem("Не синхронизированные", "unsynced")
        self.cmb_synced.currentIndexChanged.connect(self.reload_sheep)

        self.btn_sheep_edit = QPushButton("Редактировать овцу")
        self.btn_sheep_edit.clicked.connect(self.edit_selected_sheep)
        self.btn_sheep_refresh = QPushButton("Обновить")
        self.btn_sheep_refresh.clicked.connect(self.reload_sheep)

        filters.addWidget(QLabel("Поиск:"))
        filters.addWidget(self.ed_sheep_search, 1)
        filters.addWidget(QLabel("Пол:"))
        filters.addWidget(self.cmb_gender)
        filters.addWidget(QLabel("Оплата:"))
        filters.addWidget(self.cmb_paid)
        filters.addWidget(QLabel("Синхронизация:"))
        filters.addWidget(self.cmb_synced)
        filters.addWidget(self.btn_sheep_edit)
        filters.addWidget(self.btn_sheep_refresh)
        layout.addLayout(filters)

        self.tbl_sheep = QTableWidget(0, 9, self)
        self.tbl_sheep.setHorizontalHeaderLabels(
            ["ID", "ID №", "Кличка", "Пол", "Дата рождения", "Владелец", "Окрас", "Синхр.", "Оплата"]
        )
        self.tbl_sheep.setSortingEnabled(True)
        self.tbl_sheep.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_sheep.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_sheep.setAlternatingRowColors(True)
        self.tbl_sheep.itemDoubleClicked.connect(lambda _: self.edit_selected_sheep())
        self.tbl_sheep.setStyleSheet(TABLE_STYLE)
        header = self.tbl_sheep.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        layout.addWidget(self.tbl_sheep, 1)

        self.tabs.addTab(tab, "Овцы и бараны")

    def reload_owners(self):
        if db is None:
            return

        regions = get_owner_regions(db, User)
        current_region = self.cmb_owner_region.currentData() if self.cmb_owner_region.count() else ""
        self.cmb_owner_region.blockSignals(True)
        self.cmb_owner_region.clear()
        self.cmb_owner_region.addItem("Все", "")
        for region in regions:
            self.cmb_owner_region.addItem(_display_region(region), region)
        index = self.cmb_owner_region.findData(current_region)
        self.cmb_owner_region.setCurrentIndex(index if index >= 0 else 0)
        self.cmb_owner_region.blockSignals(False)

        rows = get_owner_rows(
            db,
            User,
            Sheep,
            Owner,
            self.ed_owner_search.text(),
            self.cmb_owner_region.currentData() or "",
        )
        self.tbl_owners.setSortingEnabled(False)
        self.tbl_owners.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            user = row["user"]
            values = [
                str(user.id),
                str(user.name or ""),
                str(user.username or ""),
                str(user.phone or ""),
                _display_region(user.region),
                _display_area(user.area),
                str(user.city or ""),
                str(row["sheep_count"]),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, user.id)
                self.tbl_owners.setItem(row_index, col, item)
        self.tbl_owners.setSortingEnabled(True)
        self.statusBar().showMessage(f"Владельцев: {len(rows)}")

    def reload_sheep(self):
        if db is None:
            return

        rows = get_sheep_rows(
            db,
            Sheep,
            User,
            Color,
            self.ed_sheep_search.text(),
            self.cmb_gender.currentData() or "",
            self.cmb_paid.currentData() or "",
            self.cmb_synced.currentData() or "",
        )
        self.tbl_sheep.setSortingEnabled(False)
        self.tbl_sheep.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            sheep = row["sheep"]
            gender = "Баран" if (sheep.gender or "") == "B" else "Матка"
            values = [
                str(sheep.id),
                str(sheep.id_n or ""),
                str(sheep.nick or ""),
                gender,
                sheep.dob.strftime("%d.%m.%Y") if sheep.dob else "",
                row["owner_name"],
                row["color_name"],
                "Да" if bool(getattr(sheep, "synced", False)) else "Нет",
                "Да" if bool(getattr(sheep, "is_paid", False)) else "Нет",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, sheep.id)
                self.tbl_sheep.setItem(row_index, col, item)
        self.tbl_sheep.setSortingEnabled(True)
        self.statusBar().showMessage(f"Овец: {len(rows)}")

    def edit_selected_sheep(self):
        current_row = self.tbl_sheep.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Овцы", "Выберите овцу или барана в таблице.")
            return

        item = self.tbl_sheep.item(current_row, 0)
        sheep_id = item.data(Qt.UserRole) if item is not None else None
        if sheep_id is None:
            QMessageBox.warning(self, "Овцы", "Не удалось определить запись овцы.")
            return

        sheep = db.query(Sheep).filter_by(id=sheep_id, is_deleted=False).first()
        if sheep is None:
            QMessageBox.warning(self, "Овцы", "Овца не найдена.")
            return

        editor = SheepCreateWindow(owner_id=getattr(sheep, "owner_id", None), parent=self)
        editor.prev = self
        editor.load_for_edit(sheep.id)
        editor.created.connect(lambda _sid: self.reload_sheep())
        editor.showMaximized()
        self.hide()

    def edit_selected_owner(self):
        current_row = self.tbl_owners.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Владельцы", "Выберите владельца в таблице.")
            return

        item = self.tbl_owners.item(current_row, 0)
        owner_id = item.data(Qt.UserRole) if item is not None else None
        if owner_id is None:
            QMessageBox.warning(self, "Владельцы", "Не удалось определить владельца.")
            return

        owner = db.query(User).filter_by(id=owner_id, is_deleted=False).first()
        if owner is None:
            QMessageBox.warning(self, "Владельцы", "Владелец не найден.")
            return

        dlg = OwnerCreateDialog(self, owner=owner)
        if dlg.exec_() == dlg.Accepted:
            self.reload_owners()

    def go_back(self):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        self._suppress_restore = True
        self.close()

    def closeEvent(self, ev):
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

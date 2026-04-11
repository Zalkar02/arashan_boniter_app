from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.db_service import get_db
from services.sheep_lookup_service import search_sheep_for_picker

try:
    from db.models import Sheep
    db = get_db()
except Exception:
    db = None
    Sheep = None


class SheepPickerDialog(QDialog):
    def __init__(self, parent=None, title="Выбрать овцу", gender_filter=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 520)
        self.selected_idn = None
        self._gender = (gender_filter or "").upper()

        layout = QVBoxLayout(self)
        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText("Поиск по id_n или кличке…")
        layout.addWidget(self.ed_search)

        self.list = QListWidget(self)
        layout.addWidget(self.list, 1)

        actions = QHBoxLayout()
        layout.addLayout(actions)
        btn_cancel = QPushButton("Отмена")
        btn_ok = QPushButton("Выбрать")
        actions.addStretch(1)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._choose)
        self.list.itemDoubleClicked.connect(lambda _: self._choose())

        self.ed_search.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        if db is None or Sheep is None:
            return

        query = (self.ed_search.text() or "").strip()
        try:
            rows = search_sheep_for_picker(db, Sheep, query, self._gender, limit=120)
        except Exception:
            rows = []

        for sheep in rows:
            gender = (getattr(sheep, "gender", "") or "").upper()
            idn = getattr(sheep, "id_n", "") or ""
            nick = getattr(sheep, "nick", "") or ""

            gender_txt = "Овца" if gender == "O" else "Баран"
            item = QListWidgetItem(f"{idn or '—'} — {nick or 'без клички'} ({gender_txt})")
            item.setData(Qt.UserRole + 1, idn)
            self.list.addItem(item)

        if self.list.count() == 0:
            self.list.addItem(QListWidgetItem("Ничего не найдено"))

    def _choose(self):
        item = self.list.currentItem()
        if not item:
            QMessageBox.warning(self, "Выбор", "Выберите запись")
            return

        idn = item.data(Qt.UserRole + 1) or ""
        if not idn:
            return

        self.selected_idn = idn
        self.accept()

# history.py — экран истории бонитировок
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence

try:
    from db.models import init_db, Sheep, Application, User
    db = init_db()
except Exception as e:
    db = None
    Sheep = None
    Application = None
    User = None
    _db_error = str(e)
else:
    _db_error = None


RANK_LABEL = {
    "E": "Элита",
    "1": "1-й",
    "2": "2-й",
    "B": "Брак",
}


class HistoryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История бонитировок")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self.showMaximized()

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#FFFFFF"))
        pal.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(pal)

        root = QWidget(self)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("История бонитировок")
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 6)
        tf.setBold(True)
        title.setFont(tf)
        header.addWidget(title)
        header.addStretch(1)
        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        header.addWidget(self.btn_back)
        v.addLayout(header)

        search_row = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск по ID, кличке или владельцу…")
        self.btn_refresh = QPushButton("Обновить")
        search_row.addWidget(self.ed_search, 1)
        search_row.addWidget(self.btn_refresh)
        v.addLayout(search_row)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels([
            "Дата", "ID №", "Кличка", "Владелец",
            "Класс", "Вес", "Оценка",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        v.addWidget(self.table, 1)

        self.btn_back.clicked.connect(self.close)
        self.btn_refresh.clicked.connect(self.reload)
        self.ed_search.textChanged.connect(self.reload)

        self.reload()

    def reload(self):
        if db is None or Application is None or Sheep is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
            return

        q = (self.ed_search.text() or "").strip().casefold()

        try:
            rows = (
                db.query(Application)
                .join(Sheep, Application.sheep_id == Sheep.id)
                .order_by(Application.date.desc().nullslast(), Application.id.desc())
                .all()
            )
        except Exception:
            rows = []

        filtered = []
        for app in rows:
            s = app.sheep
            if s is None:
                continue
            owner_name = (s.owner.name if getattr(s, "owner", None) else "")
            hay = " ".join([
                str(getattr(s, "id_n", "") or ""),
                str(getattr(s, "nick", "") or ""),
                owner_name or "",
            ]).casefold()
            if q and q not in hay:
                continue
            filtered.append((app, s, owner_name))

        self.table.setRowCount(len(filtered))
        for r, (app, s, owner_name) in enumerate(filtered):
            date_txt = app.date.strftime("%d.%m.%Y") if app.date else ""
            rank_txt = RANK_LABEL.get(app.rank, app.rank or "")
            weight_txt = "" if app.weight is None else str(app.weight)
            ext_txt = "" if app.exterior is None else str(app.exterior)

            items = [
                QTableWidgetItem(date_txt),
                QTableWidgetItem(str(s.id_n or "")),
                QTableWidgetItem(str(s.nick or "")),
                QTableWidgetItem(owner_name),
                QTableWidgetItem(rank_txt),
                QTableWidgetItem(weight_txt),
                QTableWidgetItem(ext_txt),
            ]
            for it in items:
                it.setFlags(it.flags() ^ Qt.ItemIsEditable)
            for c, it in enumerate(items):
                self.table.setItem(r, c, it)

        self.table.resizeColumnsToContents()

    def closeEvent(self, ev):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)


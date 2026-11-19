# history.py — экран истории бонитировок
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, QObject, QThread, pyqtSignal
from sqlalchemy.orm import sessionmaker
from PyQt5.QtGui import QPalette, QColor, QKeySequence
from owner_history_detail import OwnerHistoryDetailWindow
from services.db_service import get_db
from services.history_service import (
    build_owner_history_summary, filter_owner_history, format_owner_history_row,
)

try:
    from db.models import Sheep, Application, User, Owner
    db = get_db()
except Exception as e:
    db = None
    Sheep = None
    Application = None
    User = None
    Owner = None
    _db_error = str(e)
else:
    _db_error = None

class _SummaryWorker(QObject):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, bind):
        super().__init__()
        self._bind = bind

    def run(self):
        # сессия из get_db() не потокобезопасна — отдельная сессия на поток
        session = None
        try:
            session = sessionmaker(bind=self._bind)()
            rows = build_owner_history_summary(session, Application, Sheep, Owner, User)
            self.done.emit(rows)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            self.finished.emit()


class HistoryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress_restore = False
        self._page = 1
        self._page_size = 10
        self._total = 0
        self._all_rows = []
        self._filtered_rows = []
        self._first_show = True
        self._thread = None
        self._worker = None
        self._reload_pending = False
        self.setWindowTitle("История хозяйств")
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
        title = QLabel("История хозяйств")
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 6)
        tf.setBold(True)
        title.setFont(tf)
        header.addWidget(title)
        header.addStretch(1)
        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        header.addWidget(self.btn_back)
        self.btn_open = QPushButton("Открыть хозяйство")
        self.btn_open.setShortcut(QKeySequence("Return"))
        header.addWidget(self.btn_open)
        v.addLayout(header)

        search_row = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск по хозяйству, телефону или населённому пункту…")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self.btn_refresh = QPushButton("Обновить")
        search_row.addWidget(self.ed_search, 1)
        search_row.addWidget(self.btn_refresh)
        v.addLayout(search_row)

        pager = QHBoxLayout()
        self.btn_prev = QPushButton("← Назад")
        self.btn_next = QPushButton("Вперёд →")
        self.lbl_page = QLabel("Страница 1")
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.btn_next)
        pager.addStretch(1)
        pager.addWidget(self.lbl_page)
        v.addLayout(pager)

        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels([
            "Хозяйство", "Телефон", "Населённый пункт", "Всего овец",
            "С бонитировкой", "Без бонитировки", "Новых за 30 дней", "Не оплачено",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet(
            """
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
        )
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        for column in range(3, 8):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        v.addWidget(self.table, 1)

        self.btn_back.clicked.connect(self.go_back)
        self.btn_open.clicked.connect(self.open_owner_detail)
        self.btn_refresh.clicked.connect(self._load_summary)
        self.ed_search.textChanged.connect(lambda: self._search_timer.start())
        self.table.itemDoubleClicked.connect(lambda _: self.open_owner_detail())
        self.btn_prev.clicked.connect(lambda: self._change_page(-1))
        self.btn_next.clicked.connect(lambda: self._change_page(1))
        self._search_timer.timeout.connect(lambda: self._apply_filter(reset_page=True))

        self._load_summary()

    def showEvent(self, ev):
        super().showEvent(ev)
        if self._first_show:
            self._first_show = False
            return
        if ev.spontaneous():
            # разворачивание из свёрнутого состояния — данные не менялись
            return
        self._load_summary()

    def _load_summary(self):
        if db is None or Application is None or Sheep is None or Owner is None or User is None:
            QMessageBox.critical(self, "База данных", _db_error or "Недоступна")
            return
        if self._thread is not None:
            self._reload_pending = True
            return
        try:
            db.expire_all()
        except Exception:
            pass
        self.btn_refresh.setEnabled(False)
        self.statusBar().showMessage("Загрузка…")
        thread = QThread(self)
        worker = _SummaryWorker(db.get_bind())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_summary_loaded)
        worker.failed.connect(self._on_summary_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_summary_loaded(self, rows):
        self._all_rows = rows
        # при обновлении остаёмся на текущей странице (_update_pager сам её ограничит)
        self._apply_filter(reset_page=False)

    def _on_summary_failed(self, message):
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "Ошибка БД", message)

    def _on_thread_finished(self):
        thread, worker = self._thread, self._worker
        self._thread = None
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()
        self.btn_refresh.setEnabled(True)
        if self._reload_pending:
            self._reload_pending = False
            self._load_summary()

    def _apply_filter(self, reset_page: bool = True):
        self._filtered_rows = filter_owner_history(self._all_rows, self.ed_search.text())
        if reset_page:
            self._page = 1
        self._render_page()

    def _render_page(self):
        self._total = len(self._filtered_rows)
        self._update_pager()
        start = max(0, (self._page - 1) * self._page_size)
        page_rows = self._filtered_rows[start:start + self._page_size]

        self.table.setRowCount(len(page_rows))
        for r, row in enumerate(page_rows):
            values = format_owner_history_row(row)
            items = [QTableWidgetItem(value) for value in values]
            for it in items:
                it.setFlags(it.flags() ^ Qt.ItemIsEditable)
            if items:
                items[0].setData(Qt.UserRole, row["owner_id"])
            for c, it in enumerate(items):
                self.table.setItem(r, c, it)

        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(2, 220)
        self.statusBar().showMessage(f"Хозяйств: {self._total}")

    def _update_pager(self):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        if self._page > total_pages:
            self._page = total_pages
        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < total_pages)
        self.lbl_page.setText(f"Страница {self._page} из {total_pages}")

    def _change_page(self, step: int):
        self._page += step
        if self._page < 1:
            self._page = 1
        self._render_page()

    def open_owner_detail(self):
        item = self.table.currentItem()
        if item is None:
            QMessageBox.information(self, "Хозяйство", "Выберите хозяйство в таблице.")
            return

        owner_item = self.table.item(item.row(), 0)
        owner_id = owner_item.data(Qt.UserRole) if owner_item is not None else None
        if owner_id is None:
            QMessageBox.warning(self, "Хозяйство", "Не удалось определить хозяйство.")
            return

        self.next = OwnerHistoryDetailWindow(owner_id, self)
        self.next.prev = self
        self.next.show()
        self.hide()

    def go_back(self):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        self._suppress_restore = True
        self.close()

    def _stop_worker(self):
        thread = self._thread
        if thread is not None:
            try:
                thread.quit()
                thread.wait(10000)
            except RuntimeError:
                pass

    def closeEvent(self, ev):
        self._reload_pending = False
        self._stop_worker()
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

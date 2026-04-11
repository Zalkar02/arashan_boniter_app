# settings.py — настройки и смена пользователя
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QProgressDialog, QComboBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QKeySequence

from auth_state import AuthState
from services.auth_service import clear_session
from services.passport_print_service import (
    get_back_print_order,
    get_print_batch_size,
    get_saved_printer,
    list_system_printers,
    save_back_print_order,
    save_print_batch_size,
    save_selected_printer,
)
from services.sync_worker import SyncWorker
from services.update_worker import UpdateWorker
from services.user_context_service import get_current_user_name


class SettingsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress_restore = False
        self.sync_worker = None
        self.sync_dialog = None
        self.update_worker = None
        self.update_dialog = None
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

        user_name = get_current_user_name(AuthState.user)
        self.lbl_user = QLabel(f"Текущий пользователь: {user_name or '—'}")
        v.addWidget(self.lbl_user)

        printer_row = QHBoxLayout()
        self.lbl_printer = QLabel("Принтер:")
        self.cmb_printer = QComboBox()
        self.btn_refresh_printers = QPushButton("Обновить список")
        printer_row.addWidget(self.lbl_printer)
        printer_row.addWidget(self.cmb_printer, 1)
        printer_row.addWidget(self.btn_refresh_printers)
        v.addLayout(printer_row)

        self.lbl_printer_hint = QLabel("")
        v.addWidget(self.lbl_printer_hint)

        batch_row = QHBoxLayout()
        self.lbl_batch = QLabel("Печать за раз:")
        self.cmb_print_batch = QComboBox()
        for value in [5, 10, 15, 20]:
            self.cmb_print_batch.addItem(str(value), value)
        batch_row.addWidget(self.lbl_batch)
        batch_row.addWidget(self.cmb_print_batch)
        batch_row.addStretch(1)
        v.addLayout(batch_row)

        back_order_row = QHBoxLayout()
        self.lbl_back_order = QLabel("Оборот печатать:")
        self.cmb_back_order = QComboBox()
        self.cmb_back_order.addItem("В прямом порядке", "forward")
        self.cmb_back_order.addItem("В обратном порядке", "reverse")
        back_order_row.addWidget(self.lbl_back_order)
        back_order_row.addWidget(self.cmb_back_order)
        back_order_row.addStretch(1)
        v.addLayout(back_order_row)

        update_row = QHBoxLayout()
        self.btn_check_updates = QPushButton("Проверить обновления")
        self.btn_pull_updates = QPushButton("Обновить приложение")
        update_row.addWidget(self.btn_check_updates)
        update_row.addWidget(self.btn_pull_updates)
        update_row.addStretch(1)
        v.addLayout(update_row)

        self.lbl_update_status = QLabel("Обновления не проверялись.")
        v.addWidget(self.lbl_update_status)

        row = QHBoxLayout()
        self.btn_sync = QPushButton("Синхронизация")
        self.btn_logout = QPushButton("Сменить пользователя")
        self.btn_back = QPushButton("Назад")
        self.btn_back.setShortcut(QKeySequence("Esc"))
        row.addWidget(self.btn_sync)
        row.addWidget(self.btn_logout)
        row.addStretch(1)
        row.addWidget(self.btn_back)
        v.addLayout(row)

        self.btn_sync.clicked.connect(self._sync)
        self.btn_logout.clicked.connect(self._logout)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_refresh_printers.clicked.connect(self._load_printers)
        self.cmb_printer.currentIndexChanged.connect(self._save_printer_selection)
        self.cmb_print_batch.currentIndexChanged.connect(self._save_print_batch_size)
        self.cmb_back_order.currentIndexChanged.connect(self._save_back_print_order)
        self.btn_check_updates.clicked.connect(self._check_updates)
        self.btn_pull_updates.clicked.connect(self._pull_updates)

        self._load_printers()
        self._load_print_batch_size()
        self._load_back_print_order()

    def _load_printers(self):
        saved_printer = get_saved_printer()
        printers = list_system_printers()

        self.cmb_printer.blockSignals(True)
        self.cmb_printer.clear()
        self.cmb_printer.addItem("По умолчанию системы", "")
        for printer in printers:
            self.cmb_printer.addItem(printer, printer)

        if saved_printer:
            index = self.cmb_printer.findData(saved_printer)
            if index >= 0:
                self.cmb_printer.setCurrentIndex(index)
            else:
                self.cmb_printer.addItem(f"{saved_printer} (сохранён)", saved_printer)
                self.cmb_printer.setCurrentIndex(self.cmb_printer.count() - 1)
        else:
            self.cmb_printer.setCurrentIndex(0)
        self.cmb_printer.blockSignals(False)

        if printers:
            self.lbl_printer_hint.setText("Выбранный принтер будет использоваться для печати племкарт.")
        else:
            self.lbl_printer_hint.setText("Принтеры не найдены. Проверь CUPS и подключение принтера.")

    def _save_printer_selection(self):
        save_selected_printer(self.cmb_printer.currentData() or "")

    def _load_print_batch_size(self):
        saved_batch = get_print_batch_size()
        index = self.cmb_print_batch.findData(saved_batch)
        self.cmb_print_batch.setCurrentIndex(index if index >= 0 else self.cmb_print_batch.count() - 1)

    def _save_print_batch_size(self):
        save_print_batch_size(self.cmb_print_batch.currentData() or 20)

    def _load_back_print_order(self):
        saved_order = get_back_print_order()
        index = self.cmb_back_order.findData(saved_order)
        self.cmb_back_order.setCurrentIndex(index if index >= 0 else 0)

    def _save_back_print_order(self):
        save_back_print_order(self.cmb_back_order.currentData() or "forward")

    def _sync(self):
        if self.sync_worker is not None and self.sync_worker.isRunning():
            return

        self.sync_worker = SyncWorker(self)
        self.sync_worker.finished_ok.connect(self._on_sync_finished)
        self.sync_worker.cancelled.connect(self._on_sync_cancelled)
        self.sync_worker.failed.connect(self._on_sync_failed)
        self.sync_worker.progress.connect(self._on_sync_progress)
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("Продолжение...")
        self._create_sync_dialog()
        self.statusBar().showMessage("Синхронизация выполняется...")
        self.sync_worker.start()

    def _create_sync_dialog(self):
        self.sync_dialog = QProgressDialog("Подготовка синхронизации...", "Остановить", 0, 0, self)
        self.sync_dialog.setWindowTitle("Синхронизация")
        self.sync_dialog.setWindowModality(Qt.WindowModal)
        self.sync_dialog.setMinimumDuration(0)
        self.sync_dialog.setAutoClose(False)
        self.sync_dialog.setAutoReset(False)
        self.sync_dialog.canceled.connect(self._request_stop_sync)
        self.sync_dialog.show()

    def _request_stop_sync(self):
        if self.sync_worker is None:
            return
        self.sync_worker.stop()
        if self.sync_dialog is not None:
            self.sync_dialog.setLabelText("Останавливаем синхронизацию...")
            self.sync_dialog.setCancelButton(None)

    def _on_sync_progress(self, stage: str, model_name: str, current: int, total: int, message: str):
        if self.sync_dialog is None:
            return
        if total > 0:
            if self.sync_dialog.maximum() != total:
                self.sync_dialog.setRange(0, total)
            self.sync_dialog.setValue(min(current, total))
        else:
            self.sync_dialog.setRange(0, 0)
        self.sync_dialog.setLabelText(message or "Синхронизация...")

    def _on_sync_finished(self):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Синхронизация")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        self.statusBar().showMessage("Синхронизация завершена.", 5000)
        QMessageBox.information(self, "Синхронизация", "Синхронизация завершена.")
        self.sync_worker = None

    def _start_update_worker(self, mode: str, title: str, label: str):
        if self.update_worker is not None and self.update_worker.isRunning():
            return
        self.update_worker = UpdateWorker(mode, self)
        self.update_worker.finished_ok.connect(self._on_update_finished)
        self.update_worker.failed.connect(self._on_update_failed)
        self.btn_check_updates.setEnabled(False)
        self.btn_pull_updates.setEnabled(False)
        self.update_dialog = QProgressDialog(label, None, 0, 0, self)
        self.update_dialog.setWindowTitle(title)
        self.update_dialog.setWindowModality(Qt.WindowModal)
        self.update_dialog.setMinimumDuration(0)
        self.update_dialog.setAutoClose(False)
        self.update_dialog.setAutoReset(False)
        self.update_dialog.show()
        self.update_worker.start()

    def _check_updates(self):
        self._start_update_worker("check", "Проверка обновлений", "Проверяем обновления из main...")

    def _pull_updates(self):
        self._start_update_worker("pull", "Обновление приложения", "Загружаем обновления из main...")

    def _on_update_finished(self, result: dict):
        mode = self.update_worker.mode if self.update_worker is not None else "check"
        self.btn_check_updates.setEnabled(True)
        self.btn_pull_updates.setEnabled(True)
        if self.update_dialog is not None:
            self.update_dialog.close()
            self.update_dialog = None

        if mode == "pull":
            after = result.get("after") or {}
            self.lbl_update_status.setText(
                f"Обновление завершено. Ветка: {after.get('branch', '—')}, новых коммитов впереди нет."
            )
            QMessageBox.information(
                self,
                "Обновление",
                "Обновление загружено из main.\nПерезапустите приложение, чтобы применить изменения.",
            )
        else:
            branch = result.get("branch", "—")
            behind = result.get("behind", 0)
            ahead = result.get("ahead", 0)
            dirty = result.get("dirty", False)
            if result.get("has_updates"):
                text = f"Есть обновления: {behind} коммит(ов) в main. Текущая ветка: {branch}."
            else:
                text = f"Обновлений нет. Текущая ветка: {branch}."
            if ahead:
                text += f" Локально впереди на {ahead} коммит(ов)."
            if dirty:
                text += " Есть локальные изменения."
            self.lbl_update_status.setText(text)
            QMessageBox.information(self, "Обновления", text)
        self.update_worker = None

    def _on_update_failed(self, message: str):
        self.btn_check_updates.setEnabled(True)
        self.btn_pull_updates.setEnabled(True)
        if self.update_dialog is not None:
            self.update_dialog.close()
            self.update_dialog = None
        self.lbl_update_status.setText("Не удалось проверить или загрузить обновления.")
        QMessageBox.warning(self, "Обновления", message)
        self.update_worker = None

    def _on_sync_cancelled(self):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Продолжить синхронизацию")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        self.statusBar().showMessage("Синхронизация остановлена.", 5000)
        QMessageBox.information(self, "Синхронизация", "Синхронизация остановлена. Можно продолжить позже.")
        self.sync_worker = None

    def _on_sync_failed(self, message: str):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Продолжить синхронизацию")
        if self.sync_dialog is not None:
            self.sync_dialog.close()
            self.sync_dialog = None
        self.statusBar().showMessage("Синхронизация завершилась с ошибкой.", 5000)
        QMessageBox.warning(self, "Синхронизация", f"Не удалось выполнить синхронизацию.\n{message}")
        self.sync_worker = None

    def closeEvent(self, ev):
        if self.sync_worker is not None and self.sync_worker.isRunning():
            QMessageBox.information(self, "Синхронизация", "Дождитесь завершения синхронизации.")
            ev.ignore()
            return
        if self.update_worker is not None and self.update_worker.isRunning():
            QMessageBox.information(self, "Обновления", "Дождитесь завершения проверки или обновления.")
            ev.ignore()
            return
        if self._suppress_restore:
            super().closeEvent(ev)
            return
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        super().closeEvent(ev)

    def go_back(self):
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.show()
        self._suppress_restore = True
        self.close()

    def _logout(self):
        from login import LoginWindow
        clear_session()
        self.next = LoginWindow()
        self.next.show()
        self.close()
        prev = getattr(self, "prev", None)
        if prev is not None:
            prev.close()

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from services.update_service import can_self_update
from services.update_worker import UpdateWorker


class UpdateController(QObject):
    """Проверка и установка обновлений: окна, прогресс, перезапуск."""

    status_changed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.widget = parent_widget
        self.worker = None
        self.dialog = None
        self.silent = True
        self.required = False

    def is_busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def check(self, silent: bool = True):
        if self.is_busy():
            return
        self.silent = silent
        self.status_changed.emit("Проверяем обновления...")
        self._start(UpdateWorker("check", parent=self), self._on_checked)

    def _start(self, worker, on_ok):
        self.worker = worker
        worker.finished_ok.connect(on_ok)
        worker.failed.connect(self._on_failed)
        self.busy_changed.emit(True)
        worker.start()

    def _finish_worker(self):
        self.worker = None
        self.busy_changed.emit(False)

    def _on_checked(self, info: dict):
        self._finish_worker()
        current = info["current_version"]
        latest = info["latest_version"]
        if not info["has_updates"]:
            self.status_changed.emit(f"Версия {current}. Обновлений нет.")
            if not self.silent:
                QMessageBox.information(self.widget, "Обновления", f"У вас последняя версия {current}.")
            return

        self.required = info["required"]
        self.status_changed.emit(f"Версия {current}. Доступна новая версия {latest}.")
        if not can_self_update():
            if not self.silent:
                QMessageBox.information(
                    self.widget,
                    "Обновления",
                    f"Доступна версия {latest}. Автообновление работает только в установленном приложении.",
                )
            return
        self._prompt(info)

    def _prompt(self, info: dict):
        box = QMessageBox(self.widget)
        box.setWindowTitle("Доступно обновление")
        box.setIcon(QMessageBox.Information)
        text = f"Доступна версия {info['latest_version']} (у вас {info['current_version']})."
        if info["required"]:
            text += "\nЭта версия обязательна: старая больше не поддерживается."
        if info["notes"]:
            text += f"\n\nЧто нового:\n{info['notes']}"
        box.setText(text)
        install_btn = box.addButton("Обновить сейчас", QMessageBox.AcceptRole)
        if not info["required"]:
            box.addButton("Позже", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is install_btn:
            self._install(info)
        elif info["required"]:
            QApplication.quit()

    def _install(self, info: dict):
        self.dialog = QProgressDialog("Скачиваем обновление...", None, 0, 100, self.widget)
        self.dialog.setWindowTitle("Обновление")
        self.dialog.setWindowModality(Qt.WindowModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.setValue(0)
        self.dialog.show()
        worker = UpdateWorker("install", info, self)
        worker.progress.connect(self._on_progress)
        self._start(worker, self._on_installed)

    def _on_progress(self, done: int, total: int):
        if self.dialog is None:
            return
        if total > 0:
            self.dialog.setValue(min(99, int(done * 100 / total)))
        else:
            self.dialog.setRange(0, 0)

    def _close_dialog(self):
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def _on_installed(self, _result: dict):
        self._close_dialog()
        self._finish_worker()
        self.status_changed.emit("Устанавливаем обновление, приложение перезапустится...")
        QApplication.quit()

    def _on_failed(self, message: str):
        was_install = self.dialog is not None
        self._close_dialog()
        self._finish_worker()
        self.status_changed.emit("Не удалось проверить или установить обновление.")
        if was_install or not self.silent:
            QMessageBox.warning(self.widget, "Обновления", message)
        if was_install and self.required:
            QApplication.quit()

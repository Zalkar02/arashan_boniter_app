"""Фоновая синхронизация и значок её состояния внизу окон.

Один контроллер на приложение: только он создаёт SyncWorker, поэтому две
синхронизации одновременно не запускаются. Автосинхронизация идёт через
AUTO_SYNC_FIRST_DELAY после входа и затем раз в AUTO_SYNC_INTERVAL; кнопки
синхронизации в окнах тоже берут работника отсюда.
"""
import datetime
import os

from PyQt5.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

from auth_state import AuthState
from services.auth_service import load_tokens
from services.sync_worker import SyncWorker


def _env_seconds(name, default):
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


AUTO_SYNC_FIRST_DELAY = _env_seconds("ARASHAN_AUTO_SYNC_FIRST_DELAY", 5)
AUTO_SYNC_INTERVAL = _env_seconds("ARASHAN_AUTO_SYNC_INTERVAL", 10 * 60)
STATUS_WIDGET_NAME = "syncStatusLabel"


_CONNECTION_ERROR_MARKERS = (
    "max retries exceeded",
    "newconnectionerror",
    "failed to establish a new connection",
    "name or service not known",
    "failed to resolve",
    "getaddrinfo failed",
    "timed out",
    "connection aborted",
    "connection reset",
    "remote end closed connection",
)


def _is_connection_error(message):
    text = str(message or "").casefold()
    return any(marker in text for marker in _CONNECTION_ERROR_MARKERS)


def _short(message, limit=80):
    message = " ".join(str(message or "").split())
    return message if len(message) <= limit else message[: limit - 1] + "…"


class SyncController(QObject):
    status_changed = pyqtSignal(str, str)  # текст, подсказка
    sync_finished = pyqtSignal(bool)  # True — успешно

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls(QApplication.instance())
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._worker_is_auto = False
        self._last_success = None
        self._status = ("Синхронизация: ещё не выполнялась", "")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_tick)
        self._first_timer = QTimer(self)
        self._first_timer.setSingleShot(True)
        self._first_timer.timeout.connect(self._auto_tick)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self, wait_ms=15000):
        """При выходе дать синхронизации остановиться между порциями.

        Иначе Qt уничтожит работающий поток и приложение упадёт при закрытии.
        """
        self.stop_auto()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.stop()
            worker.wait(wait_ms)

    # --- автосинхронизация -------------------------------------------------

    def start_auto(self):
        # окна, показанные до создания контроллера (главное меню), тоже получают значок
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMainWindow) and widget.isVisible():
                self.attach_status(widget)
        self._first_timer.start(AUTO_SYNC_FIRST_DELAY * 1000)
        self._timer.start(AUTO_SYNC_INTERVAL * 1000)

    def stop_auto(self):
        self._first_timer.stop()
        self._timer.stop()

    def _can_sync(self):
        tokens = load_tokens() or {}
        return bool(AuthState.user) and bool(tokens.get("access") or tokens.get("refresh"))

    def _auto_tick(self):
        if self.is_busy():
            return
        if not self._can_sync():
            self._set_status("Синхронизация: вход не выполнен", "Войдите, чтобы данные синхронизировались.")
            return
        worker = self.create_worker(auto=True)
        if worker is not None:
            worker.start()

    # --- работники ---------------------------------------------------------

    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def create_worker(self, owner_id=None, auto=False):
        """Новый SyncWorker или None, если синхронизация уже идёт.

        Окно само подключает свои сигналы и вызывает start().
        """
        if self._worker is not None:
            return None
        worker = SyncWorker(self, owner_id=owner_id)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished_ok)
        worker.cancelled.connect(self._on_cancelled)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda w=worker: self._on_thread_finished(w))
        self._worker = worker
        self._worker_is_auto = auto
        self._set_status("Синхронизация: идёт…", "")
        return worker

    def _on_thread_finished(self, worker):
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _on_progress(self, stage, model_name, current, total, message):
        self._set_status(f"Синхронизация: {_short(message or '…', 60)}", message or "")

    def _on_finished_ok(self):
        self._last_success = datetime.datetime.now()
        self._set_status(
            f"Синхронизировано в {self._last_success:%H:%M}",
            "Данные отправлены на сервер и получены с него.",
        )
        self.sync_finished.emit(True)

    def _on_cancelled(self):
        self._set_status(self._idle_text("остановлена"), "")
        self.sync_finished.emit(False)

    def _on_failed(self, message):
        minutes = max(1, AUTO_SYNC_INTERVAL // 60)
        offline = _is_connection_error(message)
        details = "Нет интернета или сервер недоступен." if offline else message
        self._set_status(
            self._idle_text("нет связи с сервером" if offline else "ошибка"),
            f"{details}\n\nСледующая попытка автоматически через {minutes} мин.",
        )
        self.sync_finished.emit(False)

    def _idle_text(self, what):
        text = f"Синхронизация: {what}"
        if self._last_success is not None:
            text += f" (последняя успешная в {self._last_success:%H:%M})"
        return text

    # --- значок в окнах ----------------------------------------------------

    def _set_status(self, text, tooltip):
        self._status = (text, tooltip)
        self.status_changed.emit(text, tooltip)

    def status(self):
        return self._status

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QMainWindow):
            self.attach_status(obj)
        return False

    def attach_status(self, window):
        if window.findChild(QLabel, STATUS_WIDGET_NAME) is not None:
            return
        label = QLabel()
        label.setObjectName(STATUS_WIDGET_NAME)
        label.setStyleSheet("color:#555; padding:0 8px;")

        def update(text, tooltip, label=label):
            label.setText(text)
            label.setToolTip(tooltip)

        update(*self._status)
        self.status_changed.connect(update)
        label.destroyed.connect(lambda *_: self._disconnect_quietly(update))
        window.statusBar().addPermanentWidget(label)

    def _disconnect_quietly(self, slot):
        try:
            self.status_changed.disconnect(slot)
        except (TypeError, RuntimeError):
            pass

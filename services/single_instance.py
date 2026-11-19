"""Только одна копия приложения на компьютере.

Две копии пишут в одну SQLite-базу, и синхронизация одной падает с
«database is locked». На медленной Windows ярлык легко нажать дважды, а после
обновления установщик сам запускает приложение, и его окно может оказаться за
другими окнами. Поэтому вторая копия не ругается, а показывает уже открытое
окно и тихо закрывается.
"""
import hashlib
import os

from PyQt5.QtCore import QLockFile, Qt
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QMainWindow

from state_paths import STATE_DIR, ensure_state_dir

LOCK_FILE_NAME = "app.lock"
# Перезапуск после обновления на Linux стартует новую копию, пока старая
# ещё закрывается (и, возможно, дожидается остановки синхронизации).
WAIT_ENV = "ARASHAN_WAIT_FOR_PREVIOUS_INSTANCE"
DEFAULT_WAIT_MS = 2000
RESTART_WAIT_MS = 30000
ACTIVATE_MESSAGE = b"activate"
ACTIVATE_TIMEOUT_MS = 1500


def _lock_dir(lock_dir=None):
    if lock_dir is None:
        ensure_state_dir()
        lock_dir = STATE_DIR
    return lock_dir


def server_name(lock_dir=None):
    """Имя канала связи между копиями: своё для каждой папки данных (пользователя)."""
    digest = hashlib.sha1(os.path.abspath(_lock_dir(lock_dir)).encode("utf-8")).hexdigest()[:12]
    return f"arashan-boniter-{digest}"


def acquire_instance_lock(lock_dir=None, wait_ms=None):
    """Захватить блокировку. Вернуть QLockFile (держать до выхода) или None."""
    lock_dir = _lock_dir(lock_dir)
    if wait_ms is None:
        wait_ms = RESTART_WAIT_MS if os.environ.pop(WAIT_ENV, "") else DEFAULT_WAIT_MS
    lock = QLockFile(os.path.join(lock_dir, LOCK_FILE_NAME))
    # Не считать блокировку живого процесса устаревшей через 30 с (значение Qt
    # по умолчанию). Блокировка упавшего процесса снимается по PID.
    lock.setStaleLockTime(0)
    if lock.tryLock(wait_ms):
        return lock
    return None


def _allow_other_process_foreground():
    """Windows не даёт фоновому процессу вывести окно вперёд. Эту копию только
    что запустил пользователь, поэтому она может разрешить это открытой копии."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass


def request_activation(lock_dir=None, timeout_ms=ACTIVATE_TIMEOUT_MS):
    """Попросить уже открытую копию показать окно. True, если она ответила."""
    _allow_other_process_foreground()
    socket = QLocalSocket()
    socket.connectToServer(server_name(lock_dir))
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(ACTIVATE_MESSAGE)
    socket.flush()
    # flush() часто отправляет всё сразу, и тогда waitForBytesWritten ждать нечего
    ok = socket.bytesToWrite() == 0 or socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.UnconnectedState:
        socket.waitForDisconnected(timeout_ms)
    return ok


def bring_windows_to_front():
    windows = [
        widget for widget in QApplication.topLevelWidgets()
        if isinstance(widget, QMainWindow) and widget.isVisible()
    ]
    for window in windows:
        if window.isMinimized():
            window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
        window.raise_()
        window.activateWindow()
    return bool(windows)


def start_activation_server(lock_dir=None, on_activate=bring_windows_to_front, parent=None):
    """Слушать просьбы второй копии. Вернуть сервер (держать до выхода) или None."""
    name = server_name(lock_dir)
    # Канал мог остаться от упавшей копии; блокировка уже наша, значит он ничей.
    QLocalServer.removeServer(name)
    server = QLocalServer(parent)
    if not server.listen(name):
        return None

    def on_new_connection():
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()

            def on_ready(connection=connection):
                if bytes(connection.readAll()).startswith(ACTIVATE_MESSAGE):
                    on_activate()
                connection.disconnectFromServer()

            connection.readyRead.connect(on_ready)
            connection.disconnected.connect(connection.deleteLater)

    server.newConnection.connect(on_new_connection)
    return server

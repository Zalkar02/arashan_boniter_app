"""Только одна копия приложения на компьютере.

Две копии пишут в одну SQLite-базу, и синхронизация одной падает с
«database is locked». На медленной Windows ярлык легко нажать дважды.
"""
import os

from PyQt5.QtCore import QLockFile

from state_paths import STATE_DIR, ensure_state_dir

LOCK_FILE_NAME = "app.lock"
# Перезапуск после обновления на Linux стартует новую копию, пока старая
# ещё закрывается (и, возможно, дожидается остановки синхронизации).
WAIT_ENV = "ARASHAN_WAIT_FOR_PREVIOUS_INSTANCE"
DEFAULT_WAIT_MS = 2000
RESTART_WAIT_MS = 30000


def acquire_instance_lock(lock_dir=None, wait_ms=None):
    """Захватить блокировку. Вернуть QLockFile (держать до выхода) или None."""
    if lock_dir is None:
        ensure_state_dir()
        lock_dir = STATE_DIR
    if wait_ms is None:
        wait_ms = RESTART_WAIT_MS if os.environ.pop(WAIT_ENV, "") else DEFAULT_WAIT_MS
    lock = QLockFile(os.path.join(lock_dir, LOCK_FILE_NAME))
    # Блокировка упавшего процесса снимается автоматически (Qt проверяет PID).
    if lock.tryLock(wait_ms):
        return lock
    return None

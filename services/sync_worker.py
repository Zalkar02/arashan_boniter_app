from PyQt5.QtCore import QThread, pyqtSignal

from sync.sync import SyncCancelled, run_owner_sync, run_sync


class SyncWorker(QThread):
    finished_ok = pyqtSignal()
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, str, int, int, str)

    def __init__(self, parent=None, owner_id=None):
        super().__init__(parent)
        self.owner_id = owner_id
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def _should_stop(self):
        return self._stop_requested

    def _emit_progress(self, stage, model_name, current, total, message):
        self.progress.emit(stage, model_name, current, total, message)

    def run(self):
        try:
            if self.owner_id is None:
                run_sync(progress_cb=self._emit_progress, should_stop=self._should_stop)
            else:
                run_owner_sync(self.owner_id, progress_cb=self._emit_progress, should_stop=self._should_stop)
        except SyncCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()
